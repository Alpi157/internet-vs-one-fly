"""EXPLORATORY structure summaries. Numerical failures are explicit observations."""
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import eigs, ArpackNoConvergence
from flybench.calibration_v2 import unit_psp


def eigen(matrix, which):
    if matrix.nnz == 0: return dict(value=0., status='ZERO_MATRIX')
    if matrix.shape[0] <= 4:
        values = np.linalg.eigvals(matrix.toarray())
        return dict(value=float(np.max(values.real) if which=='LR' else np.max(np.abs(values))), status='COMPUTED')
    try:
        values = eigs(matrix, k=1, which=which, v0=np.ones(matrix.shape[0]), tol=1e-7, maxiter=5000, return_eigenvectors=False)
        return dict(value=float(values[0].real if which=='LR' else abs(values[0])), status='COMPUTED')
    except ArpackNoConvergence as e:
        return dict(value=None, status='ARPACK_NONCONVERGENCE', converged=len(e.eigenvalues))


def mechanism(graph):
    n=len(graph['ids']);sources=np.repeat(np.arange(n),np.diff(graph['offsets']))
    targets=graph['targets'];weights=graph['weights'].astype(float)
    matrix=csr_matrix((weights,(sources,targets)),shape=(n,n))
    effective=matrix*(.039*unit_psp()[0])
    positive=matrix.maximum(0);positive.eliminate_zeros()
    binary=positive.copy();binary.data[:]=1
    _,labels=connected_components(binary,directed=True,connection='strong')
    # Each directed cycle is counted once modulo rotations. Distinct vertices;
    # autapses are excluded from cycles and reciprocity, retained in spectra/SCC.
    cycles=positive.copy();cycles.setdiag(0);cycles.eliminate_zeros()
    b=cycles.copy();b.data[:]=1
    reciprocal=float(b.multiply(b.T).sum())
    # Row blocks bound the intermediate product for triangle counting.
    triangles=0.
    for start in range(0,n,128):
        product=cycles[start:start+128]@cycles
        triangles += float(product.multiply(cycles.T[start:start+128]).sum())
    strength=np.asarray(abs(matrix).sum(axis=0)).ravel();ordered=np.sort(strength)
    gini=float((2*np.dot(np.arange(1,n+1),ordered)/(n*ordered.sum()))-(n+1)/n) if ordered.sum() else 0.
    return dict(classification='EXPLORATORY',
        leading_signed_eigenvalue=eigen(effective,'LR'),
        excitatory_spectral_radius=eigen(positive*(.039*unit_psp()[0]),'LM'),
        excitatory_reciprocity=reciprocal/b.nnz if b.nnz else 0.,
        largest_excitatory_scc=int(np.bincount(labels).max()),
        contact_weighted_2_cycles=float(cycles.multiply(cycles.T).sum()/2),
        contact_weighted_3_cycles=triangles/3,
        in_strength_gini=gini)
