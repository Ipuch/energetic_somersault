import matplotlib.pyplot as plt
import numpy as np

from bioptim import OdeSolver, CostType, RigidBodyDynamics, Solver, DefectType, Shooting, SolutionIntegrator, \
    DynamicsFcn
from somersault import MillerOcpOnePhase, Models

import biorbd
from varint.enums import QuadratureRule

import json
import pickle


def save_results(sol, c3d_file_path):
    """
    Solving the ocp
    Parameters
    ----------
    sol: Solution
    The solution to the ocp at the current pool
    c3d_file_path: str
    The path to the c3d file of the task
    """
    data = dict(
        states=sol.states,
        controls=sol.controls,
        parameters=sol.parameters,
        iterations=sol.iterations,
        cost=sol.cost,
        detailed_cost=sol.detailed_cost,
        real_time_to_optimize=sol.real_time_to_optimize,
        status=sol.status,
        time=sol.time,
    )
    with open(f"{c3d_file_path}", "wb") as file:
        pickle.dump(data, file)


def angular_momentum_i(
        biorbd_model: biorbd.Model,
        q1: np.ndarray,
        q2: np.ndarray,
        time_step,
        discrete_approximation
) -> np.ndarray:
    """
    Compute the angular momentum of a biorbd model

    Parameters
    ----------
    biorbd_model: biorbd.Model
        The biorbd model
    q1: np.ndarray
        The generalized coordinates at the first time step
    q2: np.ndarray
        The generalized coordinates at the second time step
    time_step: float
        The time step
    discrete_approximation: QuadratureRule
        The chosen discrete approximation for the energy computing, must be chosen equal to the approximation chosen
        for the integration.

    Returns
    -------
    The discrete total energy
    """
    if discrete_approximation == QuadratureRule.MIDPOINT:
        q = (q1 + q2) / 2
    elif discrete_approximation == QuadratureRule.LEFT_APPROXIMATION:
        q = q1
    elif discrete_approximation == QuadratureRule.RIGHT_APPROXIMATION:
        q = q2
    elif discrete_approximation == QuadratureRule.TRAPEZOIDAL:
        q = (q1 + q2) / 2
    else:
        raise NotImplementedError(
            f"Discrete energy computation {discrete_approximation} is not implemented"
        )
    qdot = (q2 - q1) / time_step
    return np.linalg.norm(biorbd_model.angularMomentum(q, qdot).to_array())


def discrete_angular_momentum(
        biorbd_model: biorbd.Model,
        q: np.ndarray,
        time: np.ndarray,
        discrete_approximation: QuadratureRule = QuadratureRule.TRAPEZOIDAL,
) -> np.ndarray:
    """
    Compute the discrete total energy of a biorbd model

    Parameters
    ----------
    biorbd_model: biorbd.Model
        The biorbd model
    q: np.ndarray
        The generalized coordinates
    time: np.ndarray
        The times
    discrete_approximation: QuadratureRule
        The chosen discrete approximation for the energy computing, must be chosen equal to the approximation chosen
        for the integration, trapezoidal by default.

    Returns
    -------
    The discrete total energy
    """
    n_frames = q.shape[1]
    angular_momentum = np.zeros((n_frames - 1, 1))
    for i in range(n_frames - 1):
        angular_momentum[i] = angular_momentum_i(biorbd_model, q[:, i], q[:, i + 1], time[i + 1] - time[i],
                                                 discrete_approximation)
    return angular_momentum


def delta_angular_momentum(
        biorbd_model: biorbd.Model,
        q: np.ndarray,
        time: np.ndarray,
        discrete_approximation: QuadratureRule = QuadratureRule.TRAPEZOIDAL,
) -> np.ndarray:
    """
    Compute the delta total energy of a biorbd model

    Parameters
    ----------
    biorbd_model: biorbd.Model
        The biorbd model
    q: np.ndarray
        The generalized coordinates
    time: np.ndarray
        The times
    discrete_approximation: QuadratureRule
        The chosen discrete approximation for the energy computing, must be chosen equal to the approximation chosen
        for the integration, trapezoidal by default.

    Returns
    -------
    The discrete total energy
    """
    discrete_angular_momentum_start = angular_momentum_i(biorbd_model, q[:, 0], q[:, 1], time[1] - time[0],
                                                         discrete_approximation)
    discrete_angular_momentum_end = angular_momentum_i(biorbd_model, q[:, -2], q[:, -1], time[-2] - time[-1],
                                                       discrete_approximation)
    return discrete_angular_momentum_end - discrete_angular_momentum_start


def discrete_total_energy_i(
        biorbd_model: biorbd.Model,
        q1: np.ndarray,
        q2: np.ndarray,
        time_step,
        discrete_approximation
) -> np.ndarray:
    """
    Compute the discrete total energy of a biorbd model

    Parameters
    ----------
    biorbd_model: biorbd.Model
        The biorbd model
    q1: np.ndarray
        The generalized coordinates at the first time step
    q2: np.ndarray
        The generalized coordinates at the second time step
    time_step: float
        The time step
    discrete_approximation: QuadratureRule
        The chosen discrete approximation for the energy computing, must be chosen equal to the approximation chosen
        for the integration.

    Returns
    -------
    The discrete total energy
    """
    if discrete_approximation == QuadratureRule.MIDPOINT:
        q = (q1 + q2) / 2
    elif discrete_approximation == QuadratureRule.LEFT_APPROXIMATION:
        q = q1
    elif discrete_approximation == QuadratureRule.RIGHT_APPROXIMATION:
        q = q2
    elif discrete_approximation == QuadratureRule.TRAPEZOIDAL:
        q = (q1 + q2) / 2
    else:
        raise NotImplementedError(
            f"Discrete energy computation {discrete_approximation} is not implemented"
        )
    qdot = (q2 - q1) / time_step
    return biorbd_model.KineticEnergy(q, qdot) + biorbd_model.PotentialEnergy(q)


def discrete_total_energy(
        biorbd_model: biorbd.Model,
        q: np.ndarray,
        time: np.ndarray,
        discrete_approximation: QuadratureRule = QuadratureRule.TRAPEZOIDAL,
) -> np.ndarray:
    """
    Compute the discrete total energy of a biorbd model

    Parameters
    ----------
    biorbd_model: biorbd.Model
        The biorbd model
    q: np.ndarray
        The generalized coordinates
    time: np.ndarray
        The times
    discrete_approximation: QuadratureRule
        The chosen discrete approximation for the energy computing, must be chosen equal to the approximation chosen
        for the integration, trapezoidal by default.

    Returns
    -------
    The discrete total energy
    """
    n_frames = q.shape[1]
    discrete_total_energy = np.zeros((n_frames - 1, 1))
    for i in range(n_frames - 1):
        discrete_total_energy[i] = discrete_total_energy_i(biorbd_model, q[:, i], q[:, i + 1], time[i + 1] - time[i],
                                                           discrete_approximation)
    return discrete_total_energy


def delta_total_energy(
        biorbd_model: biorbd.Model,
        q: np.ndarray,
        time: np.ndarray,
        discrete_approximation: QuadratureRule = QuadratureRule.TRAPEZOIDAL,
) -> np.ndarray:
    """
    Compute the delta total energy of a biorbd model

    Parameters
    ----------
    biorbd_model: biorbd.Model
        The biorbd model
    q: np.ndarray
        The generalized coordinates
    time: np.ndarray
        The times
    discrete_approximation: QuadratureRule
        The chosen discrete approximation for the energy computing, must be chosen equal to the approximation chosen
        for the integration, trapezoidal by default.

    Returns
    -------
    The discrete total energy
    """
    discrete_total_energy_start = discrete_total_energy_i(biorbd_model, q[:, 0], q[:, 1], time[1] - time[0],
                                                          discrete_approximation)
    discrete_total_energy_end = discrete_total_energy_i(biorbd_model, q[:, -2], q[:, -1], time[-2] - time[-1],
                                                        discrete_approximation)
    return discrete_total_energy_end - discrete_total_energy_start


def main(ode_solver, ode_name):
    height = 2
    # --- EQUATIONS OF MOTION --- #
    # One can pick any of the following equations of motion:
    equation_of_motion = DynamicsFcn.TORQUE_DRIVEN
    # equation_of_motion = DynamicsFcn.TORQUE_DRIVEN

    model_path = Models.ACROBAT.value

    # --- Solve the program --- #
    miller = MillerOcpOnePhase(
        biorbd_model_path=model_path,
        ode_solver=ode_solver,
        dynamics_function=equation_of_motion,
        twists=2 * np.pi,  # try to add more twists with : 4 * np.pi or 6 * np.pi
        n_threads=32,  # if your computer has enough cores, otherwise it takes them all
        seed=42,  # The sens of life
        jump_height=height
    )

    miller.ocp.add_plot_penalty(CostType.ALL)

    print("number of states: ", miller.ocp.v.n_all_x)
    print("number of controls: ", miller.ocp.v.n_all_u)

    miller.ocp.print(to_console=True, to_graph=False)

    solv = Solver.IPOPT(show_online_optim=False, show_options=dict(show_bounds=True))
    solv.set_maximum_iterations(1000 * height)
    solv.set_linear_solver("ma57")
    solv.set_print_level(5)
    sol = miller.ocp.solve(solv)

    save_results(sol, f"{height}m")

    # --- Show results --- #
    # print(sol.status)
    # sol.print_cost()
    sol.graphs(show_bounds=True)

    # out = sol.integrate(
    #     shooting_type=Shooting.SINGLE,
    #     keep_intermediate_points=False,
    #     merge_phases=True,
    #     integrator=SolutionIntegrator.SCIPY_DOP853,
    # )

    # sol.animate(show_floor=False, show_gravity=False)
    q = sol.states["q"]
    model = biorbd.Model(model_path)

    dictionary = {
        "q": sol.states["q"].tolist(),
        "time": sol.time.tolist(),
    }
    # Serializing json
    json_object = json.dumps(dictionary, indent=4)

    # Writing to sample.json
    with open(ode_name + ".json", "w") as outfile:
        outfile.write(json_object)

    return (
        sol.time[:-1],
        discrete_total_energy(model, q, sol.time),
        discrete_angular_momentum(model, q, sol.time),
    )


if __name__ == "__main__":
    # --- ODE SOLVER Options --- #
    # One can pick any of the following ODE solvers:

    ode_solvers = [
        (OdeSolver.RK4(n_integration_steps=5), "RK4"),
        # (OdeSolver.COLLOCATION(defects_type=DefectType.EXPLICIT, polynomial_degree=4), "Collocation_explicit"),
        # (OdeSolver.COLLOCATION(defects_type=DefectType.IMPLICIT, polynomial_degree=4), "Collocation_implicit"),
    ]

    for ode_solver in ode_solvers:
        time, energy, angular_momentum = main(ode_solver[0], ode_solver[1])

        with open(ode_solver[1] + ".json", "r") as file:
            time_pos = json.load(file)

        model = biorbd.Model(Models.ACROBAT.value)

        time = np.asarray(time_pos["time"])
        q = np.asarray(time_pos["q"])
        energy = discrete_total_energy(model, q, time)
        angular_momentum = discrete_angular_momentum(model, q, time)
        delta_energy = delta_total_energy(model, q, time)
        delta_am = delta_angular_momentum(model, q, time)

        plt.figure(1)
        plt.plot(time[:-1], energy, label=ode_solver[1])
        plt.figure(2)
        plt.plot(time[:-1], angular_momentum, label=ode_solver[1])
        plt.figure(3)
        plt.plot(10.0, delta_energy, "+", label=ode_solver[1])
        plt.figure(4)
        plt.plot(10.0, delta_am, "+", label=ode_solver[1])

    plt.figure(1)
    plt.title("Total energy")
    plt.legend()
    plt.figure(2)
    plt.title("Angular momentum norm")
    plt.legend()
    plt.figure(3)
    plt.title("Delta energy")
    plt.legend()
    plt.figure(4)
    plt.title("Delta angular momentum")
    plt.legend()
    plt.show()
