# Project: Parametric Steering Mechanism Simulator

## 1. Project objective

Develop a complete, interactive, parametric **2D kinematic simulator for a low-cost steer-by-wire steering mechanism**, built using Onshape and intended for a real physical prototype.

The simulator must be mechanically and mathematically correct. It should be designed as an engineering tool, not merely an animation.

The primary goals are to:

1. Design and validate a mechanical steering linkage before manufacturing its components.
2. Understand how the steering geometry influences wheel angles, sensitivity, range of motion, and singularities.
3. Identify configurations that are impossible, unstable, or close to a mechanical dead point.
4. Explore different linkage dimensions using interactive controls.
5. Determine practical dimensions that can be replicated in a fully parametric Onshape CAD model.
6. Eventually introduce motor actuation and evaluate the resulting steering motion.

The intended user has good electronics and programming knowledge but limited mechanical engineering experience. The interface should therefore be intuitive while preserving mathematical rigor.

**Do not arbitrarily simplify the physical mechanism into a generic linkage that omits the wheel locations or steering brackets.**

---

## 2. Description of the physical mechanism

The mechanism is a low-cost steering system for two front wheels.

Its physical components are:

**Chassis/base**

- A rectangular stationary board.
- Approximate initial dimensions: 250 × 150 × 8 mm.
- Two fixed vertical steering pivot axes.

**Left and right steering brackets**

Each bracket consists of:

- An L-shaped metal bracket.
- A horizontal part rotating around a vertical steering pivot.
- A vertical part supporting the horizontal wheel axle.
- An additional rigid steering arm.
- A hole at the end of the steering arm to connect a tie rod.

The steering arm and L-bracket are rigidly connected. They behave as one rigid body in the kinematic simulation, even if manufactured from separate parts.

**Steering rod / tie rod**

- A rigid bar connecting the two steering arms.
- A revolute joint at each end.
- The rod may rotate and translate in the horizontal plane as the mechanism moves.
- It is not rigidly fixed to either bracket.

**Wheels**

- One wheel attached to each steering bracket.
- The wheel rotates around its horizontal axle for rolling.
- The entire wheel assembly changes steering orientation as its bracket rotates around the vertical steering pivot.
- Wheel rolling rotation is irrelevant to the initial planar kinematic analysis.

**Motor**

The existing motor is a JGA25-370 geared DC motor, nominally 12 V and approximately 58 RPM, without an integrated encoder.

The final project will use this motor to actuate the steering system, potentially through a crank and connecting rod.

The precise transmission mechanism is not yet decided, so the simulator must be modular.

### Physical manufacturing constraints

This is a simple educational prototype, not an automotive steering system.

Prefer components that can be manufactured using:

- Common metal brackets.
- Aluminum or steel flat strips.
- M4 screws and bolts.
- Washers and locknuts.
- A wooden or plastic base.
- Basic hand tools and drilling.

Avoid solutions that require CNC manufacturing, welding, specialized bearings, or complicated automotive suspension geometry.

The preliminary mechanism is a planar four-bar steering linkage. There is no requirement to implement Ackermann steering unless introduced as a future optional feature.

---

## 3. Coordinate system and geometric model

Use a consistent global 2D Cartesian coordinate system.

Suggested convention:

- X positive toward the right wheel.
- Y positive toward the rear of the chassis.
- The vehicle points toward negative Y.
- All coordinates and lengths are in millimeters.
- All internal angles are in radians.
- Display angles in degrees.

The stationary steering pivots are:

\[
A_L=(-d/2,0)
\]

\[
A_R=(d/2,0)
\]

where \(d\) is the distance between the two principal steering pivots.

### Each steering bracket is a rigid body

Each steering bracket must contain at least three characteristic points.

For the left bracket:

- \(A_L\): stationary steering pivot.
- \(B_L\): tie-rod attachment point.
- \(C_L\): wheel axle center, projected onto the top-view plane.

For the right bracket:

- \(A_R\): stationary steering pivot.
- \(B_R\): tie-rod attachment point.
- \(C_R\): wheel axle center, projected onto the top-view plane.

These points are rigidly connected on each side.

The distance \(A_iB_i\) describes the steering arm length.

The distance \(A_iC_i\) describes the physical offset between the steering pivot and wheel axle.

Importantly, these are not necessarily collinear.

Each bracket should therefore be defined using local 2D vectors:

\[
\mathbf{b}_i=B_i-A_i
\]

\[
\mathbf{c}_i=C_i-A_i
\]

defined in the bracket's local zero-steering configuration.

These two vectors are independent parameters, and together they describe the geometry of the bracket.

This approach is preferable to assuming the wheel lies along the steering arm.

### Rotation of rigid brackets

Use the standard planar rotation matrix:

\[
R(\theta)=
\begin{bmatrix}
\cos\theta&-\sin\theta\\
\sin\theta&\cos\theta
\end{bmatrix}
\]

The tie-rod attachment points are:

\[
B_L(\theta_L)=A_L+R(\theta_L)\mathbf{b}_L
\]

\[
B_R(\theta_R)=A_R+R(\theta_R)\mathbf{b}_R
\]

The wheel centers are:

\[
C_L(\theta_L)=A_L+R(\theta_L)\mathbf{c}_L
\]

\[
C_R(\theta_R)=A_R+R(\theta_R)\mathbf{c}_R
\]

The wheel heading directions must also rotate with the respective steering bracket.

Use a local zero-steering wheel forward direction:

\[
\mathbf{f}_0=(0,-1)
\]

Then:

\[
\mathbf{f}_i(\theta_i)=R(\theta_i)\mathbf{f}_0
\]

The wheel axle direction is perpendicular to the wheel's forward direction.

The simulator should render the actual wheel center and wheel heading, not just the four pivot points.

### Independent bracket geometry

Support independently configurable left/right brackets:

- Steering arm lengths.
- Steering arm initial orientations.
- Steering pivot to wheel axle offsets.
- Wheel orientation offsets if necessary.

Also provide a **symmetric mode** that links the corresponding parameters when appropriate.

Do not assume mirror symmetry means opposite steering-arm directions.

For the recommended simple parallelogram design, both steering arms point toward the rear in the neutral position.

---

## 4. Initial parameter set

The following dimensions are provisional starting values. They are not verified manufacturing dimensions.

| Parameter | Initial value | Description |
|---|---:|---|
| Base width | 250 mm | Chassis width |
| Base length | 150 mm | Chassis length |
| Base thickness | 8 mm | Physical thickness |
| Steering pivot spacing \(d\) | 180 mm | Distance between A_L and A_R |
| Left steering arm length | 25 mm | Distance A_L–B_L |
| Right steering arm length | 25 mm | Distance A_R–B_R |
| Steering arm width | 10 mm | Physical strip width |
| Steering arm thickness | 2 mm | Physical strip thickness |
| Steering arm hole diameter | 4.2 mm | Nominal M4 clearance hole |
| End material margin | 5 mm | Distance from hole center to strip endpoint |
| Left wheel axle offset | (-25, 0) mm | Local vector A_L–C_L |
| Right wheel axle offset | (+25, 0) mm | Local vector A_R–C_R |
| Steering rod joint spacing | 180 mm | Distance B_L–B_R |
| Maximum intended steering angle | ±25° | Initial target |
| Display steering range | ±45° | Initial exploration range |

The wheel axle offsets are examples and must remain editable.

The first neutral configuration should be:

\[
\mathbf{b}_L=\mathbf{b}_R=(0,25)\text{ mm}
\]

\[
\mathbf{c}_L=(-25,0)\text{ mm}
\]

\[
\mathbf{c}_R=(25,0)\text{ mm}
\]

\[
\theta_L=\theta_R=0
\]

Under this configuration:

\[
B_L=(-90,25)
\]

\[
B_R=(90,25)
\]

and the tie-rod length is exactly 180 mm.

The simulator should offer a command to calculate the required tie-rod length automatically from a chosen neutral configuration:

\[
t_{\mathrm{neutral}}=
\|B_R(0)-B_L(0)\|
\]

This prevents the user from accidentally defining an impossible starting geometry.

However, the tie-rod length must remain an independently editable physical parameter. Do not silently recalculate it after every parameter change.

If the specified length is incompatible with the intended neutral configuration, display a clear warning.

---

## 5. Four-bar linkage kinematics

The basic mechanism consists of:

- Ground link: \(A_LA_R\).
- Left steering arm: \(A_LB_L\).
- Right steering arm: \(A_RB_R\).
- Tie rod: \(B_LB_R\).

For a correctly assembled planar mechanism with fixed pivots and revolute joints, this is a one-degree-of-freedom four-bar linkage in ordinary nonsingular configurations.

Its fundamental closure equation is:

\[
\|B_R(\theta_R)-B_L(\theta_L)\|^2=t^2
\]

where \(t\) is the tie-rod length between joint centers.

Expanded:

\[
F(\theta_L,\theta_R)=
\|A_R+R(\theta_R)\mathbf b_R
-A_L-R(\theta_L)\mathbf b_L\|^2-t^2=0
\]

The implementation must solve this equation accurately.

### Primary steering input

Initially, use \(\theta_L\) as the controlled independent variable.

For each chosen \(\theta_L\), calculate all geometrically valid solutions for \(\theta_R\).

Then determine the solution belonging to the currently selected assembly branch.

Do not independently animate both steering angles.

One angle is the input, and the other must be derived from the rigid linkage constraints.

### Recommended solution method

Because the geometry is planar, an exact geometric solution is available through circle intersections.

For a given \(\theta_L\):

1. Compute the left attachment point \(B_L\).
2. The right attachment point \(B_R\) must lie on a circle centered at \(A_R\) with radius \(\|\mathbf b_R\|\).
3. It must also lie on a circle centered at \(B_L\) with radius \(t\).
4. Compute all intersections of the two circles.
5. Convert each possible \(B_R\) into a corresponding \(\theta_R\).
6. Select the correct assembly branch.

For two circles with centers \(A_R\) and \(B_L\), define:

\[
h=\|B_L-A_R\|
\]

\[
r=\|\mathbf b_R\|
\]

\[
a=\frac{r^2-t^2+h^2}{2h}
\]

\[
q^2=r^2-a^2
\]

\[
\mathbf e=\frac{B_L-A_R}{h}
\]

\[
P=A_R+a\mathbf e
\]

\[
B_R^{(\pm)}=P\pm qJ\mathbf e
\]

where:

\[
J=
\begin{bmatrix}
0&-1\\
1&0
\end{bmatrix}
\]

Finally:

\[
\theta_R=
\operatorname{atan2}(B_{Ry}-A_{Ry},B_{Rx}-A_{Rx})
-\operatorname{atan2}(b_{Ry},b_{Rx})
\]

Handle the following cases explicitly:

- Two valid circle intersections.
- Tangential intersection.
- No intersection.
- Coincident circle centers.
- Degenerate links.
- Numerical floating-point tolerance near the boundaries.

Do not use an unconstrained optimizer when an exact geometric solution is available.

A numerical root finder may still be useful for motor actuation, inverse problems, or verification.

---

## 6. Assembly branches and continuity

This is extremely important.

The existing Onshape assembly sometimes moves smoothly before suddenly snapping into an unintended configuration.

The simulator must explicitly account for this behavior.

A four-bar linkage can have multiple assembly configurations, usually referred to as different assembly branches.

The application must:

- Detect all valid solutions at a given input angle.
- Distinguish and label different branches.
- Select a branch consistent with the neutral configuration.
- Preserve branch continuity during slider movement and animation.
- Avoid switching solutions solely because one numerical result happens to be closer to a fixed reference angle.
- Allow explicit user-controlled branch selection where multiple configurations exist.
- Stop or report a toggle/singularity rather than silently jump into another branch.

Use angle unwrapping and continuity tracking when necessary.

The initial recommended configuration is the simple, uncrossed parallelogram.

---

## 7. Singularities, dead points, and sensitivity

The simulator must quantitatively identify problematic geometric configurations.

In addition to checking for intersecting or tangent circles, calculate the kinematic transmission ratio.

Define:

\[
F(\theta_L,\theta_R)=0
\]

Implicit differentiation gives:

\[
\frac{d\theta_R}{d\theta_L}
=-\frac{\partial F/\partial\theta_L}
{\partial F/\partial\theta_R}
\]

Let:

\[
\mathbf d=B_R-B_L
\]

\[
B'_i=JR(\theta_i)\mathbf b_i
\]

Then:

\[
\frac{d\theta_R}{d\theta_L}
=
\frac{\mathbf d\cdot B'_L}
{\mathbf d\cdot B'_R}
\]

when the denominator is nonzero.

Calculate and display:

- Left wheel steering angle.
- Right wheel steering angle.
- Steering angle difference.
- Transmission ratio \(d\theta_R/d\theta_L\).
- Angular mismatch between the two wheels.
- Distance from the nearest geometric toggle configuration.
- Geometric validity.
- Current assembly branch.

A small denominator in the transmission-ratio equation can imply a large output response to a small input movement.

Also detect cases where the input-side transmission becomes ineffective.

Near a singular configuration, the application should issue an explicit warning instead of displaying an arbitrarily large finite result.

A single fixed threshold should not be used without considering relevant link dimensions and numerical precision.

Use clearly defined, scale-aware numerical tolerances and configurable engineering warning thresholds.

### Steering sensitivity

Also calculate the motion of a selected tie-rod point.

Let:

\[
T=B_L+\lambda(B_R-B_L)
\]

with:

\[
0\leq\lambda\leq1
\]

By default, use \(\lambda=0.5\), the midpoint of the tie rod.

Calculate:

\[
T_x,\quad T_y
\]

and, where meaningful:

\[
\frac{dT_x}{d\theta_L},
\qquad
\frac{dT_y}{d\theta_L}
\]

This is important because the tie rod **does not necessarily move along a straight horizontal line**.

For the ideal parallelogram with rearward steering arms of length \(L\):

\[
T_x(\theta)=-L\sin\theta
\]

\[
T_y(\theta)=L\cos\theta
\]

assuming the origin lies midway between the steering pivots.

Therefore, even if the tie rod remains parallel to the X-axis, its center generally moves along a circular arc.

Do not incorrectly impose purely horizontal tie-rod motion on the four-bar mechanism.

If a future actuator constrains a point of the tie rod to move along a fixed straight line, model this as an additional constraint and check whether it overconstrains the mechanism.

---

## 8. Wheel geometry and motion

This simulator must model more than just four linkage points.

Each bracket carries a wheel, and the wheel's geometric position must be calculated using the rigid-body rotation equations.

### Wheel representation

Use parameters for:

- Wheel diameter.
- Wheel width.
- Wheel axle center relative to steering pivot.
- Initial wheel heading.
- Optional wheel mounting offset.

Draw each wheel in top view as an oriented tire rectangle or rounded rectangle, with length corresponding approximately to its diameter and width corresponding to its tire width.

Its center is \(C_i\).

Its longitudinal direction follows the rotated wheel heading vector.

### Wheel motion outputs

For each steering input:

- Position of left wheel center.
- Position of right wheel center.
- Left wheel heading.
- Right wheel heading.
- Left/right heading difference.
- Displacement of each wheel center from its neutral position.
- Wheel swept area during a steering motion.

Note that the wheel center may translate as the entire bracket rotates about a steering pivot.

This is expected and must not be discarded.

The simulator should visually show the wheel's neutral position as a dashed outline and its current position as a solid outline.

### Important modeling assumptions

This first version is a planar rigid-body simulator.

It does not calculate:

- Tire forces.
- Suspension movement.
- Road friction.
- Wheel rolling dynamics.
- Elastic deformation.
- Bearing play.
- Real-world steering torque.

Clearly document these limitations.

---

## 9. Physical geometry, clearances, and manufacturability

The mathematical links have zero thickness, but the real mechanism does not.

Provide separate parameters for:

- Steering-arm width and thickness.
- Tie-rod width and thickness.
- Hole diameters.
- Pivot diameters.
- Bolt head and washer approximate diameters.
- Wheel size.
- Base dimensions.
- End-hole margins.

For rectangular metal strips, show their actual top-view outlines rather than only their centerlines.

Provide a simple geometric interference checker for the 2D projected envelopes:

- Wheel-to-base envelope.
- Wheel-to-wheel.
- Wheel-to-steering-arm.
- Wheel-to-tie-rod.
- Steering-arm-to-other-components.

However, avoid false claims about physical collisions when two components overlap in top view but are separated vertically.

Introduce optional layer/height definitions for components, including:

- Base upper surface.
- Steering brackets.
- Steering arms.
- Tie rod.
- Washers/spacers.

A basic 2.5D clearance analysis is acceptable if properly documented.

Full 3D collision simulation is not required.

### Real construction constraints

The actual physical mechanism should be constructible with common fasteners.

For example:

- Pivot screws should be fixed relative to the base.
- Steering brackets should rotate around these screws.
- Steering arms should be rigidly fixed to the brackets, preferably using two attachment points or equivalent anti-rotation geometry.
- The tie rod should rotate freely at its two ends.
- Washers or spacers may be required to prevent rubbing.
- Locknuts should be adjusted so that joints can rotate without excessive friction.

Treat physical fastener feasibility as a design consideration, but do not pretend to calculate tolerances or structural strength without appropriate material and load data.

---

## 10. Interactive visualization

Build a responsive engineering interface.

The principal visualization must be a **to-scale top-down view** of the entire steering system.

Use equal scale for X and Y.

Include:

- Rectangular chassis outline.
- Fixed steering pivots.
- Rotating steering brackets.
- Steering arms.
- Actual tie rod.
- Tie-rod revolute joints.
- Wheel axle locations.
- Oriented wheels.
- Optional wheel neutral-position outlines.
- Selected tie-rod actuation point.
- Visible dimensions and angle annotations.
- Optional traces showing the trajectories of selected points.

Suggested colors:

- Chassis: neutral gray.
- Stationary pivots: dark blue.
- Rotating brackets: blue.
- Tie rod: orange.
- Wheels: dark gray.
- Actuation geometry: green.
- Warning configurations: red.

The goal is an easily understandable technical visualization, not a decorative illustration.

### Interactive controls

Allow editing of the geometric parameters.

Provide a steering-angle slider.

The user must be able to:

- Change geometric dimensions.
- Move the mechanism slowly.
- Play/pause an animation.
- Reset to the neutral position.
- Show/hide labels.
- Show/hide construction geometry.
- Show/hide movement trajectories.
- Select an assembly branch.
- Switch between symmetric and asymmetric designs.
- Restore default dimensions.

### Plot axes

Show a clear coordinate system and maintain a stable aspect ratio.

Avoid automatically changing the plot scale during animation, because this makes small movements difficult to interpret.

---

## 11. Diagnostic graphs

In addition to the main geometric view, provide graphs showing the mechanical response over the selected steering range.

Required graphs:

**A. Steering transmission**

\[
\theta_R=f(\theta_L)
\]

Include the ideal relation \(\theta_R=\theta_L\) as a comparison.

**B. Angular mismatch**

\[
\Delta\theta=\theta_R-\theta_L
\]

**C. Transmission ratio**

\[
k(\theta_L)=\frac{d\theta_R}{d\theta_L}
\]

**D. Tie-rod point displacement**

\[
T_x=f(\theta_L)
\]

\[
T_y=f(\theta_L)
\]

**E. Wheel-center trajectories**

Show \(C_L(\theta_L)\) and \(C_R(\theta_L)\) throughout the steering range.

**F. Singularity diagnostics**

Highlight invalid ranges, approaching toggle points, and branch boundaries.

The currently selected steering angle should be clearly marked on relevant graphs.

Graphs should distinguish numerical discontinuities from physically continuous motion.

---

## 12. Parameter exploration and design optimization

Implement a design-evaluation module.

The user should be able to specify:

- Desired maximum left steering angle.
- Desired maximum right steering angle.
- Target steering sensitivity.
- Maximum allowed left/right angular mismatch.
- Minimum allowable distance from a singular configuration.
- Available chassis dimensions.
- Allowed steering-arm lengths.
- Practical manufacturing dimensional limits.

The simulator should evaluate candidate geometries and identify suitable parameter ranges.

### Initial design target

For the simple prototype, use:

- Approximately ±25° steering range.
- Both wheels steering in the same direction.
- Approximately equal wheel steering angles.
- No singularities within the desired operating range.
- No unintended branch switching.
- No significant physical interference.
- Steering arms and tie rods manufacturable using ordinary metal strips.

The design tool should provide a clear distinction between:

- Geometrically valid.
- Kinematically well-conditioned.
- Manufacturable with the specified materials.
- Not yet mechanically verified.

### Automatic exploration

A grid search or bounded numerical optimization is acceptable.

Initially, optimize variables such as:

- Steering-arm lengths.
- Steering-arm neutral angles.
- Tie-rod length.
- Steering pivot spacing where permitted.

Keep wheel offsets as configurable dimensions and include them in clearance checks.

Do not optimize solely for steering-angle range while ignoring mechanical interference or singularities.

Give understandable reasons for rejecting candidate geometries.

---

## 13. Optional second phase: Motor-driven actuation

Once the passive steering linkage simulator is correct and tested, extend it to include motor actuation.

The existing gearmotor is a 12 V JGA25-370, approximately 58 RPM, without an encoder.

Its exact shaft dimensions, torque specifications, and mounting geometry are not yet verified.

Do not invent them.

### Suggested initial actuator topology

Use a crank-and-connecting-rod mechanism:

1. The motor rotates a crank of radius \(r\).
2. A connecting rod of length \(s\) attaches the crank pin to a selected point \(T\) on the steering linkage.
3. The crank angle \(\phi\) becomes the controlled input.
4. The resulting steering angle is obtained from the kinematic constraints.

Let the motor's fixed output-shaft center in the top-view plane be:

\[
M=(M_x,M_y)
\]

The crank pin is:

\[
Q(\phi)=M+r
\begin{bmatrix}
\cos\phi\\
\sin\phi
\end{bmatrix}
\]

The connecting rod constraint is:

\[
\|T(\theta_L,\theta_R)-Q(\phi)\|^2=s^2
\]

Together with the four-bar closure equation:

\[
\|B_R(\theta_R)-B_L(\theta_L)\|^2=t^2
\]

this defines the motor-driven motion.

Solve these equations for the steering angles given the motor angle.

Handle:

- Multiple solutions.
- Invalid configurations.
- Singularities.
- Branch selection.
- Continuity.
- Possible limits to motor rotation.

Do not assume the crank must make full 360° revolutions.

If necessary, restrict the motor to a specific angular operating range.

### Alternative actuation arrangements

Keep the implementation modular so that the selected actuator topology can later be changed.

Potential options include:

- Crank plus connecting rod.
- Direct rotation of one steering bracket.
- Gear/rack drive, as a future extension.
- Other mechanically compatible actuators.

Do not implement several complex alternatives before the basic four-bar model is working.

### Motor-related outputs

Once this phase is introduced, show:

- Motor crank angle.
- Resulting left/right wheel angles.
- Crank-to-steering transmission ratio.
- Steering-angle range.
- Crank configurations close to dead points.
- Motor angles that do not admit a valid solution.

A motor-torque calculation may be added later, but only after introducing a credible force/load model.

The kinematic model alone must not be presented as proof that the motor has sufficient torque.

A DC gearmotor without an encoder also requires consideration of position feedback or suitable limits for reliable closed-loop steering control. Do not assume that commanded motor rotation automatically corresponds to a known absolute steering position.

---

## 14. Technology and software architecture

Use Python for the computation engine.

Preferred libraries:

- NumPy for vector mathematics.
- SciPy for optimization and numerical verification where required.
- Plotly for interactive engineering plots.
- Streamlit for the initial user interface.
- Pytest for automated tests.

Choose another framework only if there is a clear technical advantage.

The simulator should run locally on Linux.

Avoid unnecessary databases, accounts, cloud dependencies, and complicated deployment systems.

### Suggested project structure

```text
steering-simulator/
├── app.py
├── steering/
│   ├── __init__.py
│   ├── parameters.py
│   ├── geometry.py
│   ├── kinematics.py
│   ├── singularities.py
│   ├── clearances.py
│   ├── optimization.py
│   └── motor.py
├── visualization/
│   ├── top_view.py
│   └── plots.py
├── configs/
│   └── default.json
├── tests/
│   ├── test_geometry.py
│   ├── test_kinematics.py
│   ├── test_singularities.py
│   └── test_motor.py
├── requirements.txt
└── README.md
```

This structure is indicative, not mandatory.

The architecture should separate:

1. Geometric parameters.
2. Rigid-body transformations.
3. Kinematic constraints.
4. Solution branch tracking.
5. Diagnostic calculations.
6. Plotting.
7. User interface.
8. Motor actuation.

Never place essential mathematical calculations exclusively inside the GUI code.

Use explicit typing and meaningful engineering variable names.

All parameter units must be documented.

Use radians internally and convert to degrees only at input/output boundaries.

---

## 15. Save, load, and CAD parameter export

The simulator must support saving and loading complete configurations.

Use JSON, including:

- Chassis geometry.
- Pivot positions.
- Bracket geometry.
- Steering-arm dimensions.
- Tie-rod length.
- Wheel dimensions.
- Desired steering-angle range.
- Selected assembly branch.
- Motor parameters when present.

Provide an export containing the relevant dimensions for Onshape.

Use human-readable variable names, for example:

```text
Interasse_sterzo = 180 mm
L_braccio_SX = 25 mm
L_braccio_DX = 25 mm
L_SteeringRod = 180 mm
Spessore_braccio = 2 mm
Larghezza_braccio = 10 mm
Diametro_foro = 4.2 mm
```

Also export the bracket-to-wheel offsets and initial arm orientations.

Onshape uses expressions such as `#Interasse_sterzo`, so the report should make the correspondence explicit.

Do not claim to automatically modify Onshape without implementing a real supported integration.

The minimum requirement is a clean export that can be manually transferred into CAD variables.

---

## 16. Mathematical validation and automated tests

This is one of the most important requirements.

A visually plausible simulation is insufficient.

Implement tests covering the following cases.

### Test 1 — Neutral parallelogram

Input:

\[
A_L=(-90,0)
\]

\[
A_R=(90,0)
\]

\[
\mathbf b_L=\mathbf b_R=(0,25)
\]

\[
t=180
\]

Expected:

\[
\theta_L=0\Rightarrow\theta_R=0
\]

The mechanism must close with negligible numerical error.

### Test 2 — Parallelogram rotation

For this ideal geometry, when following the correct assembly branch:

\[
\theta_R=\theta_L
\]

Test representative values:

- -25°
- -15°
- 0°
- +15°
- +25°

Within numerical tolerance, both sides should rotate by equal angles.

### Test 3 — Rod length conservation

For every valid configuration:

\[
\left|\|B_R-B_L\|-t\right|<\varepsilon
\]

Use a clearly defined numerical tolerance.

### Test 4 — Wheel rigid-body geometry

For every steering angle:

\[
\|C_i-A_i\|=\|\mathbf c_i\|
\]

\[
\|B_i-A_i\|=\|\mathbf b_i\|
\]

Also verify:

\[
\|C_i-B_i\|=\|\mathbf c_i-\mathbf b_i\|
\]

These tests ensure the wheel mounting position remains rigidly connected to the steering bracket.

### Test 5 — Invalid mechanism

Construct a case where the right attachment point cannot simultaneously satisfy the steering-arm and tie-rod constraints.

The simulator must report that the configuration is impossible.

It must not invent a result or silently stretch a rigid link.

### Test 6 — Tangency and singularities

Construct configurations where the two solution circles become tangent.

Verify that the simulator identifies the singularity and does not divide by zero.

### Test 7 — Solution continuity

Sweep the steering input through a valid range.

Verify that the solution remains on the selected assembly branch.

It must not suddenly flip to the alternative circle intersection.

### Test 8 — Parametric scaling

Change steering-arm length from 25 mm to 40 mm.

Verify that geometric relationships and closure constraints remain correct.

For the ideal parallelogram, test the tie-rod midpoint displacement formula:

\[
T_x=-L\sin\theta
\]

relative to the specified coordinate convention.

### Test 9 — Asymmetric geometry

Use steering arms of different lengths or orientations.

Verify that the general solver still returns a valid solution when one exists.

Do not apply parallelogram-specific shortcuts in the general solver.

### Test 10 — Motor constraints

When the motor module is introduced, verify simultaneously:

\[
\|B_R-B_L\|=t
\]

and:

\[
\|T-Q\|=s
\]

within numerical tolerance.

---

## 17. Required deliverables

The project is complete for its first major milestone when it provides:

1. A runnable local application.
2. A reliable mathematical model of the steering linkage.
3. Full rigid-body representation of the steering brackets and wheel centers.
4. Interactive adjustment of geometric parameters.
5. A top-view visualization of the mechanism.
6. Steering-angle animation.
7. Geometric validity and singularity diagnostics.
8. Steering response graphs.
9. Stable assembly-branch tracking.
10. Automated tests.
11. Configuration save/load.
12. Parameter export for Onshape.
13. Clear installation and usage instructions.

The motor-driven model can be implemented as a subsequent milestone after the passive mechanism has been validated.

---

## 18. Development strategy

Proceed incrementally.

**Milestone 1 — Mathematical core**

Implement the parameter model, rigid-body geometry, exact linkage solver, assembly branches, and tests.

Verify the basic parallelogram analytically.

**Milestone 2 — Interactive simulator**

Implement the interface, graphical mechanism, sliders, and motion visualization.

**Milestone 3 — Engineering diagnostics**

Implement transmission-ratio analysis, singularity detection, response graphs, and basic clearance checks.

**Milestone 4 — Design exploration**

Introduce target constraints, parameter sweeps, design recommendations, and CAD parameter exports.

**Milestone 5 — Motor actuation**

Introduce the JGA25-370-related crank mechanism, numerical solving, and motor-to-steering response.

Complete and validate each milestone before relying on it for the next.

If a requested feature is technically ambiguous or mechanically inappropriate, explain the concern and use a clearly documented physical assumption rather than silently implementing an arbitrary behavior.

---

## 19. Quality expectations

The final application should behave like a small engineering tool.

In particular:

- Do not fake physically impossible configurations.
- Do not deform rigid links to make an animation look correct.
- Do not silently switch assembly branches.
- Do not confuse steering-arm angle with wheel heading unless the local geometry explicitly supports that equivalence.
- Do not assume the tie rod moves purely horizontally.
- Do not confuse 2D projected overlap with confirmed 3D collision.
- Do not claim to calculate forces or motor torque from kinematics alone.
- Do not silently change physical dimensions when one slider is moved, except where explicitly linked by a selected parametric constraint.
- Handle degenerate geometries robustly.
- Use mathematical assertions and tests for important invariants.

The application must allow exploration of geometries that do not work, clearly explaining **why** they do not work.

A very important feature is the ability to distinguish:

- A linkage that is impossible to assemble.
- A valid linkage that is close to a dead point.
- A valid linkage with poor transmission characteristics.
- A valid linkage with good kinematics but physical interference.
- A well-conditioned linkage suitable for further CAD development.

## 20. Final instruction

Start by implementing **Milestone 1**, including its automated mathematical tests, then proceed through the subsequent milestones as appropriate.

Use the provided baseline dimensions for the first working example.

Do not assume that every baseline dimension exactly matches the current Onshape model. Parameters must remain configurable.

Prioritize correctness, stable solver behavior, modularity, and clear engineering diagnostics over visual polish.

The ultimate purpose of this simulator is to help select the dimensions of a real, low-cost steering mechanism, manufacture it using readily available materials, and use the resulting CAD geometry to develop a steer-by-wire demonstrator.
