"""Shared 2D dimensions; fasteners remain decorative and inside the links."""


def display_dimensions(p):
    width = p.physical.link_width
    return {
        "arm_width": width,
        "rod_width": width,
        "bracket_width": width,
        "end_margin": width/2,
        "joint_radius": min(4.5, width*.45),
        "pin_radius": min(2.1, width*.21),
    }
