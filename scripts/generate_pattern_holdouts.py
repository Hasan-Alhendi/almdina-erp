"""Deterministic synthetic holdouts, independent of the four designer cases."""
import argparse
import hashlib
import json
from pathlib import Path
import random


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=False)
    rng=random.Random(719041)
    records=[]
    for index in range(8):
        key=f'holdout-{index+1:02d}'
        width,height=((100.,210.) if index%3==0 else (130.,260.) if index%3==1 else (122.,244.))
        count=(6,8,10,6,8,6,8,10)[index]
        rows=[]
        for family in range(count):
            # Distinct dimensions avoid the existing DXF importer ambiguity
            # between different source rows with identical geometry. Preserve
            # the rejected original cohort; this does not tune optimizer code.
            rows.append(dict(width_cm=round(rng.choice((19.7,24.3,28.6,33.4,38.2))+family*.11,2),
                length_cm=rng.choice((59.2,67.1,76.4,83.6,91.3,104.7)),
                qty=(8 if index%2==0 else rng.choice((6,8,10))),piece_type='Regular',
                allow_rotation=int(index!=6 and rng.random()<.8),
                piece_instance_id=f'{key}:regular:{family}'))
        if index>=4:
            kind='L-Shaped Corner' if index%2 else 'Clipped Corner'
            rows.insert(0,dict(width_cm=width*.42,length_cm=height*.29,qty=4,piece_type=kind,
                clipped_corner_position='Top Right',clipped_corner_width_cm=12.,clipped_corner_length_cm=17.,
                allow_rotation=int(index!=6),piece_instance_id=f'{key}:corners'))
        # The existing strict roundtrip fixture creates order-row IDs smart:N.
        # Match that fixture; arbitrary identities are tested in Domain tests.
        for position, row in enumerate(rows, 1):
            row['piece_instance_id'] = f'smart:{position}'
        payload=dict(width=width,height=height,rows=rows,
            test_settings=dict(kerf_mm=(4.,5.,6.)[index%3],trim_mm=3. if index%2 else 0.,
                               allow_mirroring=index%3!=1),
            provenance='Synthetic seed 719041 revision 3: distinct geometry; IDs match the existing strict fixture smart:N; revisions 1/2 failures retained; optimizer source remains frozen; no reference poses or designer dimensions')
        target=output/f'{key}.json'
        target.write_text(json.dumps(payload,indent=2),encoding='utf-8')
        records.append(dict(case=key,file=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                            pieces=sum(r['qty'] for r in rows)))
    (output/'index.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print(json.dumps(records,indent=2))


if __name__=='__main__':
    main()
