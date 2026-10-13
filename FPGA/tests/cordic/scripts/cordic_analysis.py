import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path


# ================================================================================
# Configuration
# ================================================================================

SCRIPT_DIR = Path(__file__).resolve().parent

INPUT_FILE = SCRIPT_DIR 		/ "../outputs/sweep/cordic_sweep.csv"
ANALYZED_FILE = SCRIPT_DIR		/ "../outputs/sweep/cordic_sweep_analyzed.csv"
CANDIDATES_FILE = SCRIPT_DIR	/ "../outputs/sweep/cordic_pareto_candidates.csv"
PLOT_FILE = SCRIPT_DIR			/ "../outputs/sweep/cordic_pareto.png"

# Parameters currently considered as "costs".
# Lower is considered better.
PARETO_PARAMETERS = [
    "iterations",
    "xy_frac_bits",
    "angle_frac_bits"
]


# ================================================================================
# Selection Rules
# ================================================================================
#
# This section contains all the rules used to decide which configurations are
# interesting enough to be synthesized.
#
# Additional rules can be added here in the future.
#
# Current selection:
#
#   1. The configuration must satisfy the angular error target.
#
#   2. Among the configurations satisfying the target, only Pareto-optimal
#      configurations are selected.
#
#      Configuration A dominates configuration B if:
#
#           A.iterations      <= B.iterations
#           A.xy_frac_bits    <= B.xy_frac_bits
#           A.angle_frac_bits <= B.angle_frac_bits
#
#      and at least one of these inequalities is strict.
#
# Therefore B is discarded because another valid configuration exists which
# requires no more resources in any of the considered design parameters.
#
# ================================================================================


def rule_target_error(data):
    return data["max_abs_error_deg"] <= data["target_error_deg"]


SELECTION_RULES = [
    ("target_error", rule_target_error),
]


def dominates(config_a, config_b):
    no_worse = True
    strictly_better = False

    for parameter in PARETO_PARAMETERS:

        if config_a[parameter] > config_b[parameter]:
            no_worse = False

        if config_a[parameter] < config_b[parameter]:
            strictly_better = True

    return no_worse and strictly_better


def find_pareto(data):
    pareto = pd.Series(False, index=data.index)

    valid_indices = data.index[data["passes_rules"]]

    for index_b in valid_indices:

        config_b = data.loc[index_b]
        dominated = False

        for index_a in valid_indices:

            if index_a == index_b:
                continue

            config_a = data.loc[index_a]

            if dominates(config_a, config_b):
                dominated = True
                break

        if not dominated:
            pareto.loc[index_b] = True

    return pareto


def apply_selection(data):
    data = data.copy()

    # Start considering every configuration valid
    data["passes_rules"] = True

    # Apply all independent selection rules
    for rule_name, rule_function in SELECTION_RULES:

        result = rule_function(data)

        data["rule_" + rule_name] = result
        data["passes_rules"] &= result

    # Pareto analysis is performed only after all other rules
    data["is_pareto"] = find_pareto(data)

    # For now, only Pareto configurations are synthesized
    data["synthesize"] = data["is_pareto"]

    # Human-readable status
    data["selection_status"] = "DOMINATED"

    data.loc[~data["passes_rules"], "selection_status"] = "FAIL_TARGET"
    data.loc[data["is_pareto"], "selection_status"] = "PARETO"

    return data


# ================================================================================
# Plot
# ================================================================================

def plot_results(data):

    fail = data[data["selection_status"] == "FAIL_TARGET"]
    dominated = data[data["selection_status"] == "DOMINATED"]
    pareto = data[data["selection_status"] == "PARETO"]


    fig = plt.figure(figsize=(11, 8))

    ax = fig.add_subplot(111, projection="3d")


    ax.scatter(
        fail["iterations"],
        fail["xy_frac_bits"],
        fail["angle_frac_bits"],
        color="lightgray",
        alpha=0.35,
        s=25,
        label="Fails target"
    )


    ax.scatter(
        dominated["iterations"],
        dominated["xy_frac_bits"],
        dominated["angle_frac_bits"],
        color="steelblue",
        alpha=0.65,
        s=35,
        label="Valid but dominated"
    )


    ax.scatter(
        pareto["iterations"],
        pareto["xy_frac_bits"],
        pareto["angle_frac_bits"],
        color="crimson",
        s=90,
        edgecolors="black",
        linewidths=0.8,
        label="Pareto / Synthesize"
    )


    # Add a label to every Pareto configuration
    for _, config in pareto.iterrows():

        label = (
            f"N={int(config['iterations'])}\n"
            f"Fxy={int(config['xy_frac_bits'])}\n"
            f"Fz={int(config['angle_frac_bits'])}"
        )

        ax.text(
            config["iterations"],
            config["xy_frac_bits"],
            config["angle_frac_bits"],
            label,
            fontsize=7
        )


    ax.set_xlabel("Iterations N")
    ax.set_ylabel("XY fractional bits Fxy")
    ax.set_zlabel("Angle fractional bits Fz")

    ax.set_title("CORDIC Design Space and Parameter Pareto Front")

    ax.legend()

    plt.tight_layout()

    plt.savefig(PLOT_FILE, dpi=300)

    plt.show()


# ================================================================================
# Main
# ================================================================================

def main():

    data = pd.read_csv(INPUT_FILE)


    required_columns = [
        "iterations",
        "xy_frac_bits",
        "angle_frac_bits",
        "max_abs_error_deg",
        "target_error_deg"
    ]


    for column in required_columns:

        if column not in data.columns:
            print(f"Missing column in CSV: {column}")
            return


    # ================================================================================
    # Selection
    # ================================================================================

    data = apply_selection(data)


    # ================================================================================
    # Save Results
    # ================================================================================

    data.to_csv(ANALYZED_FILE, index=False)


    candidates = data[data["synthesize"]].copy()

    candidates.to_csv(CANDIDATES_FILE, index=False)


    # ================================================================================
    # Summary
    # ================================================================================

    print()
    print("CORDIC design-space analysis")
    print("----------------------------------------")
    print(f"Total configurations:        {len(data)}")
    print(f"Failing target:              {(data['selection_status'] == 'FAIL_TARGET').sum()}")
    print(f"Valid but dominated:         {(data['selection_status'] == 'DOMINATED').sum()}")
    print(f"Pareto configurations:       {(data['selection_status'] == 'PARETO').sum()}")
    print()


    print("Configurations selected for synthesis:")
    print()

    if len(candidates) == 0:

        print("No configuration selected.")

    else:

        print(
            candidates[
                [
                    "iterations",
                    "xy_frac_bits",
                    "angle_frac_bits",
                    "max_abs_error_deg"
                ]
            ].to_string(index=False)
        )


    print()
    print(f"Complete analysis saved to: {ANALYZED_FILE}")
    print(f"Synthesis candidates saved to: {CANDIDATES_FILE}")
    print(f"Plot saved to: {PLOT_FILE}")


    # ================================================================================
    # Plot
    # ================================================================================

    plot_results(data)


if __name__ == "__main__":
    main()
