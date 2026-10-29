"""Small source-only witnesses shared by joint regressions and benchmarks."""


def corner(kind="L-Shaped Corner", width=20, height=20, cut_x=8, cut_y=8):
    return dict(piece_type=kind, width_cm=width, length_cm=height, qty=4,
                clipped_corner_position="Top Right", clipped_corner_width_cm=cut_x,
                clipped_corner_length_cm=cut_y, allow_rotation=1)


def regular(width, height, qty=1, **extra):
    return dict(width_cm=width, length_cm=height, qty=qty, allow_rotation=0, **extra)


def glass(width, height, margin=50):
    return dict(piece_type="Glass", width_cm=width, length_cm=height, qty=1,
                glass_margin_mm=margin, allow_rotation=0)


CASES = {
    "P4-independent": (80.6, 40.3, 0, [glass(40, 40, margin=80), corner(), regular(12, 12, 2)]),
    "P4-competing": (140.6, 100.3, 0, [glass(40, 70), corner(width=50, height=50, cut_x=20, cut_y=20),
                                    regular(28, 28), regular(35, 20)]),
    "P4-clipped": (80.6, 40.3, 0, [glass(40, 40, margin=160), corner("Clipped Corner"),
                                  regular(5, 5, 2)]),
    "P4-addon-guard": (80.6, 40.3, 0, [glass(40, 40, margin=160), corner("Clipped Corner"),
        regular(5, 5, 2, extra_back_groove=1, back_groove_reference_side="edge_long_left",
                back_groove_offset_cm=.5, back_groove_width_cm=.5,
                back_groove_start_cm=.5, back_groove_length_cm=3)]),
    "P4-dependent": (100.3, 100.3, 0, [glass(30, 30), corner(width=50, height=50, cut_x=20, cut_y=20),
                                      regular(10, 10)]),
    "P4-joint-not-best": (100, 100, 0, [glass(100, 100), corner(), regular(12, 12, 2)]),
    "P4-mixed": (121.2, 40.3, 0, [glass(40, 40, margin=80), corner(), corner('Clipped Corner'),
                                  regular(12, 12, 2), regular(5, 5, 2)]),
    "P4-regular": (100, 100, 0, [regular(40, 30, 2), regular(20, 20)]),
}


def source_rows(name):
    from copy import deepcopy
    return [dict(row, piece_instance_id=f"{name}:{i}")
            for i, row in enumerate(deepcopy(CASES[name][3]), 1)]
