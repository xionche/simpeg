from __future__ import print_function
import unittest
import numpy as np
import discretize
from SimPEG import (
    maps, data_misfit, regularization,
    inversion, optimization, inverse_problem, tests, utils
)
from SimPEG.utils import mkvc
from SimPEG.electromagnetics import resistivity as dc
from pymatsolver import Pardiso

np.random.seed(40)

TOL = 1e-5
FLR = 1e-20 # "zero", so if residual below this --> pass regardless of order

class DCProblemTestsCC(unittest.TestCase):

    def setUp(self):

        aSpacing = 2.5
        nElecs = 5

        surveySize = nElecs*aSpacing - aSpacing
        cs = surveySize / nElecs / 4

        mesh = discretize.TensorMesh([
            [(cs, 10, -1.3), (cs, surveySize / cs), (cs, 10, 1.3)],
            [(cs, 3, -1.3), (cs, 3, 1.3)],
            # [(cs, 5, -1.3), (cs, 10)]
        ], 'CN')

        srcList = dc.utils.WennerSrcList(nElecs, aSpacing, in2D=True)
        survey = dc.Survey(srcList)
        problem = dc.Problem3D_CC(mesh, rhoMap=maps.IdentityMap(mesh))
        problem.pair(survey)

        mSynth = np.ones(mesh.nC)
        dobs=problem.makeSyntheticData(mSynth)

        # Now set up the problem to do some minimization
        dmis = data_misfit.L2DataMisfit(problem, dobs)
        reg = regularization.Tikhonov(mesh)
        opt = optimization.InexactGaussNewton(
            maxIterLS=20, maxIter=10, tolF=1e-6,
            tolX=1e-6, tolG=1e-6, maxIterCG=6
        )
        invProb = inverse_problem.BaseInvProblem(dmis, reg, opt, beta=1e4)
        inv = inversion.BaseInversion(invProb)

        self.inv = inv
        self.reg = reg
        self.p = problem
        self.mesh = mesh
        self.m0 = mSynth
        self.survey = survey
        self.dmis = dmis
        self.dobs = dobs

    def test_misfit(self):
        passed = tests.checkDerivative(
            lambda m: [
                self.p.dpred(m), lambda mx: self.p.Jvec(self.m0, mx)
            ],
            self.m0,
            plotIt=False,
            num=3
        )
        self.assertTrue(passed)

    def test_adjoint(self):
        # Adjoint Test
        # u = np.random.rand(self.mesh.nC*self.survey.nSrc)
        v = np.random.rand(self.mesh.nC)
        w = np.random.rand(mkvc(self.dobs).shape[0])
        wtJv = w.dot(self.p.Jvec(self.m0, v))
        vtJtw = v.dot(self.p.Jtvec(self.m0, w))
        passed = np.abs(wtJv - vtJtw) < 1e-10
        print('Adjoint Test', np.abs(wtJv - vtJtw), passed)
        self.assertTrue(passed)

    def test_dataObj(self):
        passed = tests.checkDerivative(
            lambda m: [self.dmis(m), self.dmis.deriv(m)],
            self.m0,
            plotIt=False,
            num=3
        )
        self.assertTrue(passed)

class DCProblemTestsCC_fields(unittest.TestCase):

    def setUp(self):
        cs = 10
        nc = 20
        npad = 10
        mesh = discretize.CylMesh([
            [(cs, nc), (cs, npad, 1.3)],
            np.r_[2*np.pi],
            [(cs, npad, -1.3), (cs, nc), (cs, npad, 1.3)]
        ])

        mesh.x0 = np.r_[0., 0., -mesh.hz[:npad+nc].sum()]

        # receivers
        rx_x = np.linspace(10, 200, 20)
        rx_z = np.r_[-5]
        rx_locs = utils.ndgrid([rx_x, np.r_[0], rx_z])
        rx_list = [dc.Rx.BaseRx(rx_locs, projField="e", orientation="x")]

        # sources
        src_a = np.r_[0., 0., -5.]
        src_b = np.r_[55., 0., -5.]

        src_list = [dc.Src.Dipole(rx_list, locA=src_a, locB=src_b)]

        self.mesh = mesh
        self.sigma_map = maps.ExpMap(mesh) * maps.InjectActiveCells(
            mesh, mesh.gridCC[:, 2] <=0, np.log(1e-8)
        )
        self.prob = dc.Problem3D_CC(
            mesh, sigmaMap=self.sigma_map, Solver=Pardiso, bc_type="Dirichlet"
        )
        self.survey = dc.Survey(src_list)
        self.prob.pair(self.survey)


    def test_e_deriv(self):
        x0 = -1 + 1e-1*np.random.rand(self.sigma_map.nP)

        def fun(x):
            return self.prob.dpred(x), lambda x: self.prob.Jvec(x0, x)
        return tests.checkDerivative(fun, x0, num=3, plotIt=False)

    def test_e_adjoint(self):
        print('Adjoint Test for e')

        m = -1 + 1e-1*np.random.rand(self.sigma_map.nP)
        u = self.prob.fields(m)

        v = np.random.rand(self.survey.nD)
        w = np.random.rand(self.sigma_map.nP)

        vJw = v.dot(self.prob.Jvec(m, w, u))
        wJtv = w.dot(self.prob.Jtvec(m, v, u))
        tol = np.max([TOL*(10**int(np.log10(np.abs(vJw)))),FLR])
        print(
            "vJw: {:1.2e}, wJTv: {:1.2e}, tol: {:1.0e}, passed: {}\n".format(
                vJw, wJtv, vJw - wJtv, tol, np.abs(vJw - wJtv) < tol
            )
        )
        return np.abs(vJw - wJtv) < tol


class DCProblemTestsN(unittest.TestCase):

    def setUp(self):

        aSpacing = 2.5
        nElecs = 10

        surveySize = nElecs*aSpacing - aSpacing
        cs = surveySize / nElecs / 4

        mesh = discretize.TensorMesh([
            [(cs, 10, -1.3), (cs, surveySize / cs), (cs, 10, 1.3)],
            [(cs, 3, -1.3), (cs, 3, 1.3)],
            # [(cs, 5, -1.3), (cs, 10)]
        ], 'CN')

        srcList = dc.utils.WennerSrcList(nElecs, aSpacing, in2D=True)
        survey = dc.Survey(srcList)
        problem = dc.Problem3D_N(mesh, rhoMap=maps.IdentityMap(mesh))
        problem.pair(survey)

        mSynth = np.ones(mesh.nC)
        dobs = problem.makeSyntheticData(mSynth)

        # Now set up the problem to do some minimization
        dmis = data_misfit.L2DataMisfit(problem, dobs)
        reg = regularization.Tikhonov(mesh)
        opt = optimization.InexactGaussNewton(
            maxIterLS=20, maxIter=10, tolF=1e-6,
            tolX=1e-6, tolG=1e-6, maxIterCG=6
        )
        invProb = inverse_problem.BaseInvProblem(dmis, reg, opt, beta=1e4)
        inv = inversion.BaseInversion(invProb)

        self.inv = inv
        self.reg = reg
        self.p = problem
        self.mesh = mesh
        self.m0 = mSynth
        self.survey = survey
        self.dmis = dmis
        self.dobs = dobs

    def test_misfit(self):
        passed = tests.checkDerivative(
            lambda m: [
                self.p.dpred(m), lambda mx: self.p.Jvec(self.m0, mx)
            ],
            self.m0,
            plotIt=False,
            num=3
        )
        self.assertTrue(passed)

    def test_adjoint(self):
        # Adjoint Test
        # u = np.random.rand(self.mesh.nC*self.survey.nSrc)
        v = np.random.rand(self.mesh.nC)
        w = np.random.rand(mkvc(self.dobs).shape[0])
        wtJv = w.dot(self.p.Jvec(self.m0, v))
        vtJtw = v.dot(self.p.Jtvec(self.m0, w))
        passed = np.abs(wtJv - vtJtw) < 1e-8
        print('Adjoint Test', np.abs(wtJv - vtJtw), passed)
        self.assertTrue(passed)

    def test_dataObj(self):
        passed = tests.checkDerivative(
            lambda m: [self.dmis(m), self.dmis.deriv(m)],
            self.m0,
            plotIt=False,
            num=3
        )
        self.assertTrue(passed)


class DCProblemTestsCC_storeJ(unittest.TestCase):

    def setUp(self):

        aSpacing = 2.5
        nElecs = 5

        surveySize = nElecs*aSpacing - aSpacing
        cs = surveySize / nElecs / 4

        mesh = discretize.TensorMesh([
            [(cs, 10, -1.3), (cs, surveySize / cs), (cs, 10, 1.3)],
            [(cs, 3, -1.3), (cs, 3, 1.3)],
            # [(cs, 5, -1.3), (cs, 10)]
        ], 'CN')

        srcList = dc.utils.WennerSrcList(nElecs, aSpacing, in2D=True)
        survey = dc.Survey(srcList)
        problem = dc.Problem3D_CC(
            mesh, rhoMap=maps.IdentityMap(mesh), storeJ=True
            )
        problem.pair(survey)

        mSynth = np.ones(mesh.nC)
        dobs = problem.makeSyntheticData(mSynth)

        # Now set up the problem to do some minimization
        dmis = data_misfit.L2DataMisfit(problem, data=dobs)
        reg = regularization.Tikhonov(mesh)
        opt = optimization.InexactGaussNewton(
            maxIterLS=20, maxIter=10, tolF=1e-6,
            tolX=1e-6, tolG=1e-6, maxIterCG=6
        )
        invProb = inverse_problem.BaseInvProblem(dmis, reg, opt, beta=1e4)
        inv = inversion.BaseInversion(invProb)

        self.inv = inv
        self.reg = reg
        self.p = problem
        self.mesh = mesh
        self.m0 = mSynth
        self.survey = survey
        self.dmis = dmis
        self.dobs = dobs

    def test_misfit(self):
        passed = tests.checkDerivative(
            lambda m: [
                self.p.dpred(m), lambda mx: self.p.Jvec(self.m0, mx)
            ],
            self.m0,
            plotIt=False,
            num=3
        )
        self.assertTrue(passed)

    def test_adjoint(self):
        # Adjoint Test
        # u = np.random.rand(self.mesh.nC*self.survey.nSrc)
        v = np.random.rand(self.mesh.nC)
        w = np.random.rand(mkvc(self.dobs).shape[0])
        wtJv = w.dot(self.p.Jvec(self.m0, v))
        vtJtw = v.dot(self.p.Jtvec(self.m0, w))
        passed = np.abs(wtJv - vtJtw) < 1e-10
        print('Adjoint Test', np.abs(wtJv - vtJtw), passed)
        self.assertTrue(passed)

    def test_dataObj(self):
        passed = tests.checkDerivative(
            lambda m: [self.dmis(m), self.dmis.deriv(m)],
            self.m0,
            plotIt=False,
            num=3
        )
        self.assertTrue(passed)


class DCProblemTestsN_storeJ(unittest.TestCase):

    def setUp(self):

        aSpacing = 2.5
        nElecs = 10

        surveySize = nElecs*aSpacing - aSpacing
        cs = surveySize / nElecs / 4

        mesh = discretize.TensorMesh([
            [(cs, 10, -1.3), (cs, surveySize / cs), (cs, 10, 1.3)],
            [(cs, 3, -1.3), (cs, 3, 1.3)],
            # [(cs, 5, -1.3), (cs, 10)]
        ], 'CN')

        srcList = dc.utils.WennerSrcList(nElecs, aSpacing, in2D=True)
        survey = dc.Survey(srcList)
        problem = dc.Problem3D_N(
            mesh, rhoMap=maps.IdentityMap(mesh), storeJ=True
            )
        problem.pair(survey)

        mSynth = np.ones(mesh.nC)
        dobs = problem.makeSyntheticData(mSynth)

        # Now set up the problem to do some minimization
        dmis = data_misfit.L2DataMisfit(problem, data=dobs)
        reg = regularization.Tikhonov(mesh)
        opt = optimization.InexactGaussNewton(
            maxIterLS=20, maxIter=10, tolF=1e-6,
            tolX=1e-6, tolG=1e-6, maxIterCG=6
        )
        invProb = inverse_problem.BaseInvProblem(dmis, reg, opt, beta=1e4)
        inv = inversion.BaseInversion(invProb)

        self.inv = inv
        self.reg = reg
        self.p = problem
        self.mesh = mesh
        self.m0 = mSynth
        self.survey = survey
        self.dmis = dmis
        self.dobs = dobs

    def test_misfit(self):
        passed = tests.checkDerivative(
            lambda m: [
                self.p.dpred(m), lambda mx: self.p.Jvec(self.m0, mx)
            ],
            self.m0,
            plotIt=False,
            num=3
        )
        self.assertTrue(passed)

    def test_adjoint(self):
        # Adjoint Test
        # u = np.random.rand(self.mesh.nC*self.survey.nSrc)
        v = np.random.rand(self.mesh.nC)
        w = np.random.rand(mkvc(self.dobs).shape[0])
        wtJv = w.dot(self.p.Jvec(self.m0, v))
        vtJtw = v.dot(self.p.Jtvec(self.m0, w))
        passed = np.abs(wtJv - vtJtw) < 1e-8
        print('Adjoint Test', np.abs(wtJv - vtJtw), passed)
        self.assertTrue(passed)

    def test_dataObj(self):
        passed = tests.checkDerivative(
            lambda m: [self.dmis(m), self.dmis.deriv(m)],
            self.m0,
            plotIt=False,
            num=3
        )
        self.assertTrue(passed)

if __name__ == '__main__':
    unittest.main()
