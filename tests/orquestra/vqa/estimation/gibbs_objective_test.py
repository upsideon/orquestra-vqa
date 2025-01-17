################################################################################
# © Copyright 2021-2022 Zapata Computing Inc.
################################################################################
import numpy as np
import pytest
from orquestra.quantum.api.estimation import EstimationTask
from orquestra.quantum.api.estimator_contract import ESTIMATOR_CONTRACTS
from orquestra.quantum.circuits import Circuit, H, X
from orquestra.quantum.openfermion import IsingOperator, QubitOperator
from orquestra.quantum.testing.mocks import MockQuantumBackend

from orquestra.vqa.estimation.gibbs_objective import GibbsObjectiveEstimator


@pytest.mark.parametrize("contract", ESTIMATOR_CONTRACTS)
def test_estimator_contract(contract):
    estimator = GibbsObjectiveEstimator(alpha=0.2)
    assert contract(estimator)


class TestGibbsEstimator:
    @pytest.fixture(params=[1.0, 0.8, 0.5, 0.2])
    def estimator(self, request):
        return GibbsObjectiveEstimator(alpha=request.param)

    @pytest.fixture()
    def circuit(self):
        return Circuit([X(0)])

    @pytest.fixture()
    def operator(self):
        return IsingOperator("Z0")

    @pytest.fixture()
    def estimation_tasks(self, operator, circuit):
        return [EstimationTask(operator, circuit, 10)]

    @pytest.fixture()
    def backend(self):
        return MockQuantumBackend()

    def test_raises_exception_if_operator_is_not_ising(
        self, estimator, backend, circuit
    ):
        # Given
        estimation_tasks = [EstimationTask(QubitOperator("X0"), circuit, 10)]
        with pytest.raises(TypeError):
            estimator(
                backend=backend,
                estimation_tasks=estimation_tasks,
            )

    @pytest.mark.parametrize("alpha", [-1, 0])
    def test_gibbs_estimator_raises_exception_if_alpha_less_than_or_equal_to_0(
        self, estimator, backend, estimation_tasks, alpha
    ):
        estimator.alpha = alpha
        with pytest.raises(ValueError):
            estimator(
                backend=backend,
                estimation_tasks=estimation_tasks,
            )

    def test_gibbs_estimator_returns_correct_values(self, estimator, backend, operator):
        # Given
        estimation_tasks = [EstimationTask(operator, Circuit([H(0)]), 10000)]

        expval_0 = np.exp(1 * -estimator.alpha)  # Expectation value of bitstring 0
        expval_1 = np.exp(-1 * -estimator.alpha)  # Expectation value of bitstring 1

        # Target value is the -log of the mean of the expectation values of the 2
        # bitstrings
        target_value = -np.log((expval_1 + expval_0) / 2)

        # When
        expectation_values = estimator(
            backend=backend,
            estimation_tasks=estimation_tasks,
        )

        # Then
        assert expectation_values[0].values == pytest.approx(target_value, abs=2e-2)
