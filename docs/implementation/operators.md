# Typed composition and future events

Plan 02 M2 supplies an explicit library registry:

```python
from forecast_anything.operators import register_builtin_operators

operators = register_builtin_operators()
```

Pass that registry to `Runtime`; the initial CLI still registers only the baseline provider. No Timestral, Torch or language model is required.

- `sum_aligned`: elementwise sum of identically ordered series on identical timestamps, with the same known unit. Input roles may be arbitrary. Parameters are empty.
- `cumulative_balance`: named `inflow` and `outflow` inputs, with parameters `initial_value` (finite number) and `unit`. At each step, add inflow and subtract outflow from the previous balance. Inputs are per-step quantities in the balance unit, not rates requiring integration. The initial value is a deterministic constant applied to every path.
- `any_exceed`: one input named `value`, with finite `threshold` and strict `comparator` (`gt` or `lt`). For each complete joint path, check whether any series at any forecast timestamp satisfies the comparator. The result is the fraction of paths that satisfy the event.

Bind roles through `config.parameters.bindings` in a graph. Runtime removes bindings before passing the remaining parameters to the operator. Relations still cover exactly the graph inputs.

Transforms preserve common point and joint-path representations. Point forecasts are deterministic scenarios, not a distribution. Joint paths require matching nonempty sample counts and `sample_group_id`; path index identifies the same sampled world across inputs. Marginal quantiles are discarded when other supported representations exist, and quantile-only compositions fail with `unsupported_representation`. Inputs with only point forecasts cannot feed `any_exceed`.

The event output has series `event:any_exceed`, one timestamp at the last input timestamp, unit `probability`, and a one-cell point matrix. Quantiles, paths and sample group are absent. Assumptions retain input provenance and describe the strict comparator, threshold, all-series scope, inclusive first/last forecast timestamps, sample count and group. This is an empirical probability, without a calibration or confidence-interval claim.

## Contract compatibility and guarantees

`OperatorContract` retains Plan 01's required `name`, `required_representation` and `units_rule`. Two optional v1 fields extend negotiation:

- `accepted_representations`: nonempty unique canonical representations, including `required_representation` as the legacy fallback. Omission means only that fallback is accepted.
- `output_representation`: `preserve`, a fixed canonical representation, or absent. `preserve` guarantees the intersection of accepted representations guaranteed by every input. A fixed value guarantees that output. Omission retains legacy transform/event output semantics.

Historical `paths` and `quantiles` aliases still normalize to `joint_paths` and `marginal_quantiles`, including inside the new fields. Original v1 registrations remain accepted, and `GraphSpec`, `CompiledGraph`, forecast results and durable run wire shapes are unchanged. Extended registration serialization includes the two optional fields; consumers validating extended registrations need the updated schema.

Compilation propagates guaranteed representations, not representations that a provider might happen to return. It tracks the scalar calendar of new point probability events. Runtime recomputes the same guarantee intersection, validates actual output shape and timestamps, and verifies preserved sample identity/count. Actual source origins and cross-source timestamps are established at execution.

There is no implicit resampling, unit conversion, series renaming/reordering, independent-world coupling, rate integration or quantile-to-path reconstruction. All input series must have identical ordered IDs; all units must agree. Deterministic calendar sources remain provider known-future inputs; these operators accept forecast results, and do not invent samples from snapshots. See the [Timestral guide](timestral.md) for parity, benchmark results and weight licensing. The [experimental residual sampler](../research/joint-paths.md) can provide compatible joint paths, but its experiment did not establish calibrated joint forecast probabilities.
