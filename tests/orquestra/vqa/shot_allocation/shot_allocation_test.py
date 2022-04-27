################################################################################
# © Copyright 2021-2022 Zapata Computing Inc.
################################################################################
from functools import partial

import numpy as np
import pytest
import sympy
from orquestra.quantum.api.estimation import EstimationTask
from orquestra.quantum.circuits import RX, RY, RZ, Circuit, H, I, X
from orquestra.quantum.estimation._estimation import (
    calculate_exact_expectation_values,
    estimate_expectation_values_by_averaging,
    evaluate_estimation_circuits,
    evaluate_non_measured_estimation_tasks,
    split_estimation_tasks_to_measure,
)
from orquestra.quantum.measurements import ExpectationValues, Measurements
from orquestra.quantum.openfermion import (
    IsingOperator,
    QubitOperator,
    qubit_operator_sparse,
)
from orquestra.quantum.openfermion.zapata_utils._utils import change_operator_type
from orquestra.quantum.symbolic_simulator import SymbolicSimulator
from zquantum.core.interfaces.mock_objects import MockQuantumBackend

from orquestra.vqa.estimation.context_selection import (
    get_context_selection_circuit_for_group,
    group_greedily,
    group_individually,
    perform_context_selection,
)
from orquestra.vqa.shot_allocation._shot_allocation import (
    allocate_shots_proportionally,
    allocate_shots_uniformly,
)

h2_hamiltonian_grouped = [
    QubitOperator("-0.0420789769629383 []"),
    QubitOperator("-0.04475014401986127 [X0 X1 Y2 Y3]"),
    QubitOperator("0.04475014401986127 [X0 Y1 Y2 X3]"),
    QubitOperator("0.04475014401986127 [Y0 X1 X2 Y3]"),
    QubitOperator("-0.04475014401986127 [Y0 Y1 X2 X3]"),
    QubitOperator(
        """0.17771287459806312 [Z0] +
         0.1705973832722407 [Z0 Z1] +
         0.12293305054268083 [Z0 Z2] +
         0.1676831945625421 [Z0 Z3] +
         0.17771287459806312 [Z1] +
         0.1676831945625421 [Z1 Z2] +
         0.12293305054268083 [Z1 Z3] +
         -0.24274280496459985 [Z2] +
         0.17627640802761105 [Z2 Z3] +
         -0.24274280496459985 [Z3]"""
    ),
]


class TestShotAllocation:
    @pytest.fixture()
    def frame_operators(self):
        operators = [
            2.0 * IsingOperator((1, "Z")) * IsingOperator((2, "Z")),
            1.0 * IsingOperator((3, "Z")) * IsingOperator((0, "Z")),
            -1.0 * IsingOperator((2, "Z")),
        ]

        return operators

    @pytest.fixture()
    def circuits(self):
        circuits = [Circuit() for _ in range(5)]

        circuits[1] += RX(1.2)(0)
        circuits[1] += RY(1.5)(1)
        circuits[1] += RX(-0.0002)(0)
        circuits[1] += RY(0)(1)

        for circuit in circuits[2:]:
            circuit += RX(sympy.Symbol("theta_0"))(0)
            circuit += RY(sympy.Symbol("theta_1"))(1)
            circuit += RX(sympy.Symbol("theta_2"))(0)
            circuit += RY(sympy.Symbol("theta_3"))(1)

        return circuits

    @pytest.mark.parametrize(
        "n_samples, target_n_samples_list",
        [
            (100, [100, 100, 100]),
            (17, [17, 17, 17]),
        ],
    )
    def test_allocate_shots_uniformly(
        self,
        frame_operators,
        n_samples,
        target_n_samples_list,
    ):
        allocate_shots = partial(allocate_shots_uniformly, number_of_shots=n_samples)
        circuit = Circuit()
        estimation_tasks = [
            EstimationTask(operator, circuit, 1) for operator in frame_operators
        ]

        new_estimation_tasks = allocate_shots(estimation_tasks)

        for task, target_n_samples in zip(new_estimation_tasks, target_n_samples_list):
            assert task.number_of_shots == target_n_samples

    @pytest.mark.parametrize(
        "total_n_shots, prior_expectation_values, target_n_samples_list",
        [
            (400, None, [200, 100, 100]),
            (400, ExpectationValues(np.array([0, 0, 0])), [200, 100, 100]),
            (400, ExpectationValues(np.array([1, 0.3, 0.3])), [0, 200, 200]),
        ],
    )
    def test_allocate_shots_proportionally(
        self,
        frame_operators,
        total_n_shots,
        prior_expectation_values,
        target_n_samples_list,
    ):
        allocate_shots = partial(
            allocate_shots_proportionally,
            total_n_shots=total_n_shots,
            prior_expectation_values=prior_expectation_values,
        )
        circuit = Circuit()
        estimation_tasks = [
            EstimationTask(operator, circuit, 1) for operator in frame_operators
        ]

        new_estimation_tasks = allocate_shots(estimation_tasks)

        for task, target_n_samples in zip(new_estimation_tasks, target_n_samples_list):
            assert task.number_of_shots == target_n_samples

    @pytest.mark.parametrize(
        "n_samples",
        [-1],
    )
    def test_allocate_shots_uniformly_invalid_inputs(
        self,
        n_samples,
    ):
        estimation_tasks = []
        with pytest.raises(ValueError):
            allocate_shots_uniformly(estimation_tasks, number_of_shots=n_samples)

    @pytest.mark.parametrize(
        "total_n_shots, prior_expectation_values",
        [
            (-1, ExpectationValues(np.array([0, 0, 0]))),
        ],
    )
    def test_allocate_shots_proportionally_invalid_inputs(
        self,
        total_n_shots,
        prior_expectation_values,
    ):
        estimation_tasks = []
        with pytest.raises(ValueError):
            _ = allocate_shots_proportionally(
                estimation_tasks, total_n_shots, prior_expectation_values
            )


@pytest.mark.parametrize(
    "frame_operators, expecval, expected_result",
    [
        (
            h2_hamiltonian_grouped,
            None,
            (
                0.5646124437984263,
                15,
                np.array(
                    [0, 0.03362557, 0.03362557, 0.03362557, 0.03362557, 0.43011016]
                ),
            ),
        ),
    ],
)
def test_estimate_nmeas_with_groups(frame_operators, expecval, expected_result):
    K2_ref, nterms_ref, frame_meas_ref = expected_result
    K2, nterms, frame_meas = estimate_nmeas_for_frames(frame_operators, expecval)
    np.testing.assert_allclose(frame_meas, frame_meas_ref)
    assert math.isclose(K2_ref, K2)
    assert nterms_ref == nterms
