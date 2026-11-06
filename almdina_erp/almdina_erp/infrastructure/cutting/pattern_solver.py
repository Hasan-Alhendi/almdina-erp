"""Bounded CBC integer coverage adapter. Never receives geometry or Frappe IO."""
import math
import time

from almdina_erp.almdina_erp.domain.cutting.pattern_master import (
    PatternSelection, ShelfSelection, valid_selection,
)


def solve_pattern_master(columns, demand, max_boards, *, deadline, hint=()):
    if time.monotonic() >= deadline:
        return PatternSelection(status='deadline')
    if (not columns or len(columns) > 256 or not demand or len(demand) > 64
            or not 0 < max_boards <= 32 or sum(demand) > 256
            or any(type(q) is not int or q <= 0 for q in demand)
            or any(len(c.counts) != len(demand) or not any(c.counts)
                or any(type(q) is not int or q < 0 for q in c.counts)
                or any(type(v) is not int or not 0 <= v <= 10**13 for v in
                    (c.remnant_units,c.cutter_units,c.internal_units,c.segments)) for c in columns)):
        return PatternSelection(status='unsupported_model')
    try:
        from ortools.linear_solver import pywraplp
        model = pywraplp.Solver.CreateSolver('CBC')
        if model is None:
            return PatternSelection(status='unavailable')
        variables = [model.IntVar(0, min(max_boards, *(demand[g]//q
            for g,q in enumerate(c.counts) if q)), f'x{i}') for i,c in enumerate(columns)]
        for g,quantity in enumerate(demand):
            model.Add(sum(v*c.counts[g] for v,c in zip(variables,columns)) == quantity)
        count = sum(variables)
        model.Add(count <= max_boards)
        owners = [model.BoolVar(f'owner{i}') for i in range(len(columns))]
        for owner,var in zip(owners,variables):
            model.Add(owner <= var)
        model.Add(sum(owners) == 1)
        remnant = sum(o*c.remnant_units for o,c in zip(owners,columns))
        length = sum(v*c.cutter_units for v,c in zip(variables,columns))
        internal = sum(v*c.internal_units for v,c in zip(variables,columns))
        segments = sum(v*c.segments for v,c in zip(variables,columns))
        phases = []
        selected = PatternSelection()
        if valid_selection(columns,demand,PatternSelection(tuple(hint)),max_boards):
            model.SetHint(variables,list(hint))
            selected = PatternSelection(tuple(hint),'hint')
        # Integer objectives in separate phases avoid unsafe giant weights.
        objectives = ((count,False),(remnant,True),(length,False),(internal,True),(segments,False))
        for phase,(objective,maximize) in enumerate(objectives):
            remaining = deadline-time.monotonic()
            if remaining <= .005:
                break
            model.SetTimeLimit(max(1,round(remaining*1000/(len(objectives)-phase))))
            if maximize:
                model.Maximize(objective)
            else:
                model.Minimize(objective)
            status = model.Solve()
            label = {0:'optimal_in_pool',1:'feasible',2:'infeasible',6:'not_solved'}.get(status,'solver_error')
            phases.append(label)
            if status not in (pywraplp.Solver.OPTIMAL,pywraplp.Solver.FEASIBLE):
                break
            values = tuple(round(v.solution_value()) for v in variables)
            proposal = PatternSelection(values,label,tuple(phases))
            if not valid_selection(columns,demand,proposal,max_boards):
                break
            selected = proposal
            value = model.Objective().Value()
            if not math.isfinite(value):
                break
            # Fix a completed feasible bound even if optimality was not proven.
            model.Add(objective >= round(value) if maximize else objective <= round(value))
            model.SetHint(variables,list(values))
        return PatternSelection(selected.multiplicities,selected.status,tuple(phases))
    except (ImportError,RuntimeError,ValueError,OverflowError):
        return PatternSelection(status='solver_error')


def solve_shelf_master(columns,demand,capacities,slot_boards,mandatory,owner,owner_limit,*,deadline):
    """Assign coherent rows globally; independent Domain validates the result."""
    if time.monotonic()>=deadline:
        return ShelfSelection(status='deadline')
    if (not demand or len(demand)>64 or sum(demand)>256 or any(type(q) is not int or q<=0 for q in demand)
            or not 0<len(columns)<=32 or len(capacities)!=len(columns) or len(slot_boards)!=len(columns)
            or not 0<len(mandatory)<=32 or not 0<=owner<len(columns) or owner_limit<0
            or sum(map(len,columns))>16384 or any(not 0<=b<len(mandatory) for b in slot_boards)
            or any(type(c) is not int or c<=0 for c in capacities)
            or any(len(c.counts)!=len(demand) or not any(c.counts) or c.thickness<=0
                or any(type(n) is not int or n<0 for n in c.counts) for choices in columns for c in choices)):
        return ShelfSelection(status='unsupported_model')
    try:
        from ortools.linear_solver import pywraplp
        model=pywraplp.Solver.CreateSolver('CBC')
        if model is None:
            return ShelfSelection(status='unavailable')
        # Select a multiset of coherent rows per equivalent width first.
        # Assigning every row to every identical board in the MIP creates a
        # large symmetric model and can miss even the first feasible answer.
        groups={}
        effective=list(capacities)
        effective[owner]=min(effective[owner],owner_limit)
        for index,choices in enumerate(columns):
            groups.setdefault(choices,[]).append(index)
        grouped=list(groups.items())
        if sum(len(choices) for choices,_ in grouped)>2048:
            return ShelfSelection(status='distinct_row_limit')
        variables=[]
        for group,(choices,slots) in enumerate(grouped):
            capacity=sum(effective[i] for i in slots)
            variables.append([model.IntVar(0,min(capacity//c.thickness,
                *(demand[g]//q for g,q in enumerate(c.counts) if q)),f'r{group}_{i}')
                for i,c in enumerate(choices)])
        for g,qty in enumerate(demand):
            model.Add(sum(v*c.counts[g] for values,(choices,_) in zip(variables,grouped)
                          for v,c in zip(values,choices))==qty)
        heights=[sum(v*c.thickness for v,c in zip(values,choices)) for values,(choices,_) in zip(variables,grouped)]
        for used,(_,slots) in zip(heights,grouped):
            model.Add(used<=sum(effective[i] for i in slots))
        model.Minimize(sum(heights))

        def pack_rows(rows,slots,pack_deadline):
            """Exact bounded 1D repair; unequal capacities and owner stay real."""
            rows.sort(key=lambda item:(-item[1],item[0]))
            space=[effective[i] for i in slots]
            assignments=[[] for _ in slots]
            failed=set()
            nodes=0
            def visit(position):
                nonlocal nodes
                nodes+=1
                if time.monotonic()>=pack_deadline or nodes>20000:
                    return False
                if position==len(rows):
                    return True
                key=(position,tuple(sorted(space[i] for i,s in enumerate(slots) if s!=owner)),
                     tuple(space[i] for i,s in enumerate(slots) if s==owner))
                if key in failed:
                    return False
                row,height=rows[position]
                seen=set()
                for index in sorted(range(len(slots)),key=lambda i:(slots[i]==owner,space[i]-height,slots[i])):
                    signature=(space[index],slots[index]==owner)
                    if height>space[index] or signature in seen:
                        continue
                    seen.add(signature)
                    space[index]-=height
                    assignments[index].append(row)
                    if visit(position+1):
                        return True
                    assignments[index].pop()
                    space[index]+=height
                failed.add(key)
                return False
            return assignments if visit(0) else None

        for attempt in range(3):
            remaining=deadline-time.monotonic()
            if remaining<=.005:
                break
            model.SetTimeLimit(max(1,round(1000*remaining/(3-attempt)*.8)))
            status=model.Solve()
            if status not in (pywraplp.Solver.OPTIMAL,pywraplp.Solver.FEASIBLE):
                return ShelfSelection(status=('restricted_cover_exhausted' if attempt else 'infeasible_in_rows')
                    if status==2 else {6:'not_solved'}.get(status,'solver_error'))
            chosen=[tuple(round(v.solution_value()) for v in values) for values in variables]
            allocations=[[0]*len(choices) for choices in columns]
            possible=True
            for values,(choices,slots) in zip(chosen,grouped):
                rows=[(r,choices[r].thickness) for r,qty in enumerate(values) for _ in range(qty)]
                packed=pack_rows(rows,slots,min(deadline,time.monotonic()+max(.03,(deadline-time.monotonic())*.4)))
                if packed is None:
                    possible=False
                    break
                for slot,members in zip(slots,packed):
                    for row in members:
                        allocations[slot][row]+=1
            if possible:
                return ShelfSelection(tuple(tuple(v) for v in allocations),'feasible')
            # Diversify after bounded packing, without claiming infeasibility
            # of the excluded multiset. Do not exclude every plan containing its
            # useful rows. All columns are nonempty, so at least one selected
            # positive multiplicity must decrease in any different exact cover.
            less=[]
            for values,previous in zip(variables,chosen):
                for var,qty in zip(values,previous):
                    if qty:
                        flag=model.BoolVar(f'less{attempt}_{len(less)}')
                        model.Add(var<=qty-1+256*(1-flag))
                        less.append(flag)
            model.Add(sum(less)>=1)
        return ShelfSelection(status='no_packable_row_cover')
    except (ImportError,RuntimeError,ValueError,OverflowError):
        return ShelfSelection(status='solver_error')
