"""Source pieces, not authored placements; P5 industrial search witnesses."""
from copy import deepcopy
from almdina_erp.tests.joint_nesting_cases import corner, regular, glass


def one(kind='L-Shaped Corner', width=40, height=40, cut_x=30, cut_y=30, **kw):
    return dict(corner(kind, width, height, cut_x, cut_y), qty=1, **kw)


CASES = {
    'P5-L-different': (45.3, 45.3, 0, [one(), one(width=35, height=35, cut_x=25, cut_y=25)]),
    'P5-L-incompatible': (45.3, 45.3, 0, [one(cut_x=3, cut_y=3),
                                           one(width=35, height=35, cut_x=2, cut_y=2)]),
    'P5-clip-different': (50.5, 45.1, 0, [one('Clipped Corner'),
        one('Clipped Corner', width=35, height=35, cut_x=25, cut_y=25)]),
}


def source_rows(name):
    return [dict(row, piece_instance_id=f'{name}:{i}')
            for i, row in enumerate(deepcopy(CASES[name][3]), 1)]
