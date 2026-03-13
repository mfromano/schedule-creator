"""Configuration for schedule optimization."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SearchConfig:
    """Configuration for local search optimization.

    Attributes:
        iterations: Maximum number of local search iterations.
        initial_temp: Initial temperature for simulated annealing.
        cooling_rate: Temperature decay rate per iteration (0 < rate < 1).
        min_temp: Minimum temperature before stopping annealing.
        swap_types: Enabled swap types ("rotation", "block", "cross").
        tabu_tenure: Number of iterations a swap remains tabu (0=disabled).
        plateau_limit: Stop after N iterations without improvement.
    """
    iterations: int = 500
    initial_temp: float = 10.0
    cooling_rate: float = 0.995
    min_temp: float = 0.1
    swap_types: list[str] = field(default_factory=lambda: ["rotation", "block", "cross"])
    tabu_tenure: int = 0
    plateau_limit: int = 100


@dataclass
class HybridConfig:
    """Configuration for hybrid Monte Carlo + local search optimization.

    Attributes:
        num_trials: Number of Monte Carlo trials to run.
        top_k_refine: Number of top trials to refine with local search.
        search_config: Local search configuration.
        shuffle_residents: Randomize resident processing order.
        shuffle_blocks: Randomize block processing order.
        top_k_sample: Sample from top K rotations during fill.
    """
    num_trials: int = 20
    top_k_refine: int = 3
    search_config: SearchConfig = field(default_factory=SearchConfig)
    shuffle_residents: bool = True
    shuffle_blocks: bool = True
    top_k_sample: int = 3
