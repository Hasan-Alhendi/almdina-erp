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
    'P5-single-guest': (40, 40, 0, [one(),regular(12,12)]),
    'P5-two-guests': (40, 40, 0, [one(),regular(12,12,2)]),
    'P5-many-guests': (40, 40, 0, [one(),regular(12,12,4)]),
    'P5-four-choices': (80.9, 50, 0, [corner(),regular(70,10,2)]),
    'P5-joint-different': (136.4, 45.3, 0, [one(),one(width=35,height=35,cut_x=25,cut_y=25),
        one('Clipped Corner'),one('Clipped Corner',width=35,height=35,cut_x=25,cut_y=25),
        glass(40,40,margin=80),regular(12,12)]),
    'P5-realistic-mixed': (122, 244, 0, [
        one(width=55,height=70,cut_x=25,cut_y=40),one(width=50,height=65,cut_x=30,cut_y=35),
        one('Clipped Corner',width=45,height=65,cut_x=25,cut_y=30),
        one('Clipped Corner',width=50,height=60,cut_x=30,cut_y=25),
        glass(70,100,margin=100),glass(65,90,margin=80),regular(20,30,4),regular(40,55,2)]),
    'P5-L-addon': (45.3,43.3,0,[one(height=38,cut_y=28,extra_liner=1,liner_reference_side='edge_long_left',
        liner_width_cm=2,liner_offset_cm=2,liner_start_cm=2,liner_length_cm=25),
        one(width=35,height=33,cut_x=25,cut_y=23)]),
    'P5-addon-ambiguous': (45.3,45.3,0,[one(extra_liner=1,liner_reference_side='edge_long_left',
        liner_width_cm=2,liner_offset_cm=2,liner_start_cm=2,liner_length_cm=25),
        one(width=35,height=35,cut_x=25,cut_y=25)]),
}


def source_rows(name):
    return [dict(row, piece_instance_id=f'{name}:{i}')
            for i, row in enumerate(deepcopy(CASES[name][3]), 1)]
