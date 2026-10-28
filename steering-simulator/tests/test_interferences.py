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
    assert len(obstacles)==6
    assert all('tirante' not in obstacle.name for obstacle in obstacles)
    # Contacts with the excluded tie rod alone do not reject the mechanism.
    assert not motor_interference(p,points,pins,())


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
    del raw['parameters']['physical']['link_width']
    assert from_json(json.dumps(raw)).physical.link_width==10.
    with pytest.raises(ValueError):
        replace(p,physical=replace(p.physical,link_width=0)).validate()
