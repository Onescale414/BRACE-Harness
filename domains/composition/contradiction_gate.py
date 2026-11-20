"""Propose one source-bound impossibility witness on the active solver budget."""
import composition_checker as arithmetic
import contradiction_checker as proof
import learning_solver as solver


if (tuple(solver.OPS) != proof.OPS or tuple(arithmetic.OPS) != proof.OPS
        or solver.MODULI != proof.MODULI
        or (solver.MAX_STEPS, solver.MAX_INPUT, solver.MAX_VALUE) != (4, 10**6, 10**48)):
    raise RuntimeError('contradiction-grammar-mismatch')


class CheckedContradiction(solver.Stop):
    """Only the independent verifier can authorize this terminal decision."""


def detect(search, source, metrics):
    constraints = search.band_constraints
    metrics['constraint_reads'] += len(constraints)
    if len(constraints) != 16:
        return None
    for offset, modulus in enumerate(proof.MODULI):
        group = constraints[offset * 4:(offset + 1) * 4]
        for a in range(4):
            for b in range(a + 1, 4):
                search.budget.deadline()
                metrics['row_pairs'] += 1
                metrics['input_residue_comparisons'] += 1
                if group[a][2] != group[b][2]:
                    continue
                metrics['output_residue_comparisons'] += 1
                if group[a][3] != group[b][3]:
                    metrics['source_bytes_hashed'] += len(source)
                    return dict(profile=proof.PROFILE, grammar=proof.GRAMMAR,
                                source_sha256=proof.sha(source), modulus=modulus, rows=[a, b])
    return None


def check_witness(source, witness, budget):
    budget.deadline()
    if budget.work['full_checks'] >= solver.MAX_CHECKS:
        raise solver.Stop('check-budget')
    budget.work['full_checks'] += 1
    result = proof.verify(source, witness)
    budget.work['checker_scalar_operations'] += result['scalar_operations']
    budget.deadline()
    return result


def try_refuse(search, source, out):
    budget = search.budget
    budget.deadline()
    if search.priority:
        return
    if budget.work['full_checks'] >= solver.MAX_CHECKS:
        raise solver.Stop('check-budget')
    metrics = dict(constraint_reads=0, row_pairs=0, input_residue_comparisons=0,
                   output_residue_comparisons=0, source_bytes_hashed=0)
    out['contradiction_scan'] = metrics
    witness = detect(search, source, metrics)
    if witness is None:
        return
    budget.take_slot()
    checked = check_witness(source, witness, budget)
    out['contradiction'] = {'certificate': witness, 'verification': checked}
    if checked['status'] == 'checked-contradiction':
        raise CheckedContradiction('checked-contradiction')
