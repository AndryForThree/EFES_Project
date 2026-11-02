"""Focused checks for actual 2D contacts, travel sampling and persisted widths."""
from dataclasses import replace
import json
import math
import numpy as np
import pytest
from steering.geometry import rectangle, strip
from steering.interferences import Obstacle, motor_interference, overlaps, prepare_obstacles, strips
from steering.motor import at_steering
from steering.motor_search import sample_steering
from steering.parameters import Motor, Parameters, from_json, to_json


def test_rectangle_contacts_rotations_and_rendered_strip_agree():
    first=np.array([rectangle(np.array([0.,0.]),2,8)])
    crossing=np.array([rectangle(np.array([0.,0.]),2,8,math.pi/2)])
    touching=np.array([rectangle(np.array([2.,0.]),2,8)])
    separate=np.array([rectangle(np.array([2.01,0.]),2,8)])
    assert overlaps(first,crossing)[0]
    assert overlaps(first,touching)[0]
    assert not overlaps(first,separate)[0]
    actual=strips(np.array([[1.,2.]]),np.array([[6.,8.]]),4)[0]
    expected=strip(np.array([1.,2.]),np.array([6.,8.]),4,2)
    assert all(any(np.allclose(corner,other) for other in expected) for corner in actual)


def test_interference_at_interior_pose_and_excluded_tie_rod():
    p=replace(Parameters(),motor=Motor(0.,40.,10.,40.))
    pins=np.array([[10.,40.]]*3)
    points=np.array([[25.,10.],[0.,0.],[-25.,10.]])
    obstacle=Obstacle('braccio SX',np.tile(rectangle(np.array([5.,20.]),2.,2.),(3,1,1)))
    assert not motor_interference(p,points[:1],pins[:1],(Obstacle(obstacle.name,obstacle.polygons[:1]),))
    assert 'astina motore / braccio SX' in motor_interference(p,points,pins,(obstacle,))
    samples=sample_steering(Parameters(),.1,3)
    obstacles=prepare_obstacles(Parameters(),samples.left_angles,samples.right_angles)
    assert len(obstacles)==7
    assert obstacles[-1].name=='tirante' and obstacles[-1].links_exempt


def test_real_side_mounted_crank_is_rejected_and_obstacles_match_pose():
    p=replace(Parameters(),motor=Motor(-90.,40.,20.,90.,-1))
    samples=sample_steering(p,.1,3)
    obstacles=prepare_obstacles(p,samples.left_angles,samples.right_angles)
    states=[at_steering(p,float(m)) for m in samples.means]
    assert all(states)
    pins=np.array([s.pin for s in states])
    assert motor_interference(p,samples.points,pins,obstacles)
    for index,m in enumerate(samples.means):
        pose=states[index].pose
        wheel=rectangle(pose.c_left,p.physical.wheel_width,p.physical.wheel_diameter,pose.heading_left)
        assert np.allclose(obstacles[0].polygons[index],wheel)


def test_width_roundtrip_validation_and_old_config_import():
    p=replace(Parameters(),physical=replace(Parameters().physical,link_width=14.))
    assert from_json(to_json(p))==p
    raw=json.loads(to_json(p));raw['schema_version']=5
    raw.pop('coordinate_origin')
    raw['parameters']['motor']['x']-=p.pivot_spacing/2
    del raw['parameters']['physical']['link_width']
    del raw['parameters']['physical']['q_joint_diameter']
    assert from_json(json.dumps(raw)).physical.link_width==10.
    with pytest.raises(ValueError):
        replace(p,physical=replace(p.physical,link_width=0)).validate()


def test_q_disk_contacts_include_rotated_edges_and_corners():
    from steering.interferences import circle_overlaps_rectangle
    box=np.array([rectangle(np.array([0.,0.]),2.,2.,math.pi/4)])
    point=np.array([[0.,2*math.sqrt(2)]])  # rotation of (2, 2)
    assert circle_overlaps_rectangle(point,math.sqrt(2),box)[0]
    assert not circle_overlaps_rectangle(point,1.4,box)[0]
    assert circle_overlaps_rectangle(np.array([[0.,0.]]),.1,box)[0]


def test_q_reservation_checks_tie_rod_while_its_links_may_overlap_it():
    p=Parameters()
    obstacles=prepare_obstacles(p,np.array([0.]),np.array([0.]))
    tie=(obstacles[-1],)
    points=np.array([[0.,25.]])
    pins=np.array([[0.,35.]])  # tie upper edge Y=30; Q radius=5 touches
    assert motor_interference(p,points,pins,tie)=='Interferenza 2D: giunto Q / tirante'
    pins[0,1]=35.01
    assert not motor_interference(p,points,pins,tie)
    larger=replace(p,physical=replace(p.physical,q_joint_diameter=12.))
    assert 'giunto Q / tirante' in motor_interference(larger,points,pins,tie)
    raw=json.loads(to_json(larger))
    assert from_json(to_json(larger)).physical.q_joint_diameter==12.
    raw['schema_version']=6
    raw.pop('coordinate_origin')
    raw['parameters']['motor']['x']-=larger.pivot_spacing/2
    del raw['parameters']['physical']['q_joint_diameter']
    assert from_json(json.dumps(raw)).physical.q_joint_diameter==10.
    with pytest.raises(ValueError):
        replace(p,physical=replace(p.physical,q_joint_diameter=0)).validate()


def test_rear_clearance_follows_current_rod_and_complete_crank_outline():
    from steering.interferences import crank_rear_clearance
    p=replace(Parameters(),motor=Motor(0.,8.,2.,10.),
              physical=replace(Parameters().physical,link_width=2.))
    pins=np.array([[2.,8.],[2.,8.]])
    starts=np.array([[-10.,0.],[-7.,3.]])
    ends=np.array([[10.,0.],[7.,17.]])  # rod moves and inclines during travel
    rod=Obstacle('tirante',strips(starts,ends,2.),links_exempt=True)
    assert crank_rear_clearance(p,pins[:1],(Obstacle('tirante',rod.polygons[:1]),))==pytest.approx(6.)
    gap=crank_rear_clearance(p,pins,(rod,))
    assert gap<0  # neutral alone would have accepted this mechanism
    rotation=np.array([[0.,-1.],[1.,0.]])
    center=rotation@np.array([p.motor.x,p.motor.y])
    rotated=replace(p,motor=replace(p.motor,x=center[0],y=center[1]))
    assert crank_rear_clearance(rotated,pins@rotation.T,(Obstacle('tirante',rod.polygons@rotation.T),))==pytest.approx(gap)
    touching=replace(p,motor=replace(p.motor,y=2.))
    assert crank_rear_clearance(touching,np.array([[2.,2.]]),(Obstacle('tirante',rod.polygons[:1]),))==pytest.approx(0.)


@pytest.mark.parametrize('label',['SX','DX'])
def test_b_reservation_catches_links_and_q_outside_thin_arm(label):
    p=replace(Parameters(),physical=replace(Parameters().physical,link_width=2.,q_joint_diameter=10.))
    joint=np.array([[0.,0.]])
    arm=Obstacle('braccio '+label,strips(np.array([[0.,-20.]]),joint,2.),joint_center=joint)
    points=np.array([[10.,4.]])
    pins=np.array([[-10.,4.]])
    rod_case=replace(p,motor=Motor(-10.,14.,10.,20.))
    assert motor_interference(rod_case,points,pins,(arm,))==f'Interferenza 2D: astina motore / giunto B {label}'
    small=replace(rod_case,physical=replace(p.physical,q_joint_diameter=2.))
    assert not motor_interference(small,points,pins,(arm,))
    lever_case=replace(p,motor=Motor(-10.,4.,20.,10.))
    assert motor_interference(lever_case,np.array([[20.,4.]]),np.array([[10.,4.]]),(arm,))==f'Interferenza 2D: leva motore / giunto B {label}'
    q_case=replace(p,motor=Motor(7.,13.,10.,20.))
    assert motor_interference(q_case,np.array([[20.,3.]]),np.array([[7.,3.]]),(arm,))==f'Interferenza 2D: giunto Q / giunto B {label}'


def test_b_clearance_checks_interior_pose_and_local_shared_attachment_only():
    p=replace(Parameters(),motor=Motor(-10.,14.,10.,20.),
              physical=replace(Parameters().physical,link_width=2.,q_joint_diameter=10.))
    joints=np.array([[0.,-20.],[0.,0.],[0.,-20.]])
    obstacles=(Obstacle('braccio SX',strips(joints+[0.,-20.],joints,2.),joint_center=joints),)
    points=np.tile([10.,4.],(3,1));pins=np.tile([-10.,4.],(3,1))
    assert not motor_interference(p,points[:1],pins[:1],
                                  (Obstacle('braccio SX',obstacles[0].polygons[:1],joint_center=joints[:1]),))
    assert 'giunto B SX' in motor_interference(p,points,pins,obstacles)
    joint=joints[1:2]
    arm=Obstacle('braccio SX',strips(joint+[0.,-20.],joint,2.),joint_center=joint)
    connected=replace(p,motor=Motor(-10.,11.,10.,11.))
    assert not motor_interference(connected,joint,np.array([[0.,11.]]),(arm,))
    # Being merely close to B is not an intentional shared joint.
    assert 'giunto B SX' in motor_interference(connected,joint+[0.,.01],np.array([[0.,11.]]),(arm,))
    crossing=replace(p,motor=Motor(-17.,-30.,10.,31.))
    assert motor_interference(crossing,joint,np.array([[-7.,-30.]]),(arm,))=='Interferenza 2D: astina motore / braccio SX'
