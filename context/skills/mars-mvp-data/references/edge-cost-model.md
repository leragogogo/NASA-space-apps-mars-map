# Edge cost and resource model (per profile)

Status (2026-11-14):
- **Decided:** one graph, one topology, both profiles. Every directed edge stores, per profile, a routing `cost` plus resource consumption.
- **Proposed, not confirmed by the product owner:** every formula, constant and unit below. Constants are placeholders that live in config; `formula_version` is saved with the graph. Do not present placeholder numbers as real suit or rover specifications.

Parent doc: `../SKILL.md` section 10 (routing). Layer inputs to the graph: `layer-ingestion.md`.

## 1. What the graph stores

Logical view of one edge (the shape everyone reasons about; numbers are illustrative):

```python
edge = {
    "astronaut": {"cost": 10.0,  "time_s": 95.0, "o2_g": 154.0, "co2_g": 180.0, "water_g": 302.0, "energy_wh": 8.0},
    "car":       {"cost": 324.0, "time_s": 41.0, "o2_g": 134.0, "co2_g": 150.0, "water_g": 123.0, "energy_wh": 95.0},
}
```

Physical storage is **struct-of-arrays**, not a dict per edge. About 2.6M directed edges as Python dicts would take multiple GB; as float32 arrays, 2 profiles x 6 attributes is ~125 MB.

- Graph topology: `src[m]`, `dst[m]`. The edge id is the index into every array.
- One array per `(profile, attribute)`, named `<profile>__<attr>` (e.g. `astronaut__cost`, `car__energy_wh`), all length `m`.
- `app/graph/` exposes `edge_attrs(edge_id) -> dict` returning the logical view above, for the API, debugging and tests.
- Every edge has every attribute for every profile. Impassable for a profile = `cost = inf` and all its other attributes `inf`. Such an edge is never on a returned path (the solver treats the pair as unreachable).
- `cost` and the resources are >= 0 and never NaN (the Dijkstra needs non-negative, non-NaN weights). Dtypes: `cost` float64 (the solver sums many of them), resources float32. `app/graph/attrs.py` enforces that an impassable edge has `cost` and every resource inf together.

## 2. Canonical attributes and units

Defined once in `app/core/resources.py` (units are proposed; changing one is a `formula_version` bump). Adding a resource later means adding a name there plus a formula per profile; the graph arrays are generic.

| Attribute | Unit | Meaning |
|---|---|---|
| `cost` | flat-equivalent metres | The only thing the solver minimises. On flat ground with `alpha + beta = 1`, `cost = L`. |
| `time_s` | s | Travel time. Sum = EVA / drive duration. |
| `o2_g` | g | Oxygen consumed. |
| `co2_g` | g | CO2 produced = load on the CO2 removal system. |
| `water_g` | g | Water consumed for thermal control and hydration. |
| `energy_wh` | Wh | Battery or electrical energy. Astronaut: suit power. Car: traction + auxiliary. |

Not modelled as edge attributes (MVP): radiation (shelter distance would be a node attribute, future), thermal environment, communications, electrolytes. No data in our datasets.

## 3. Shared edge geometry

Inputs, for edge `u -> v` (signed, so uphill and downhill differ):
- `d` horizontal distance (m): `R * sqrt(dlat^2 + (cos(lat_mid) * dlon)^2)` in radians, with `R = 3,396,190 m` (the project sphere).
- `dz = elev[v] - elev[u]`, `L = sqrt(d^2 + dz^2)`.
- `i = dz / d` (gradient, signed), `theta = atan(i)`.
- Optional: roughness at `v` (relief layer, `roughness_m`).

Elevation comes from the relief ingestion's `elev_m` (the same array the slope overlay is derived from).

## 4. Cost function (both profiles)

```
cost = L * s(theta) * [ alpha * (v_flat / v(i))  +  beta * (e(i) / e_flat) ]
s(theta) = 1 + (|theta| / theta_max)^p          # smooth margin before the hard limit
theta > theta_max  ->  cost = inf               # hard limit
```

- `v(i)` speed (m/s) and `e(i)` energy per metre on this edge, from the profile formulas below. `v_flat = v(0)`, `e_flat = e(0)`.
- Both ratios equal 1 on flat ground, so with `alpha + beta = 1`, `cost = L` there. Defaults: `alpha = beta = 0.5` (to calibrate).
- `alpha`, `beta`, `p` are per-profile config. Profile presets (fastest / lowest energy) change `alpha` and `beta`. They are not request parameters in the MVP.
- **Weather risk is deliberately not in the cost.** Weights are precomputed once and the season is a request parameter (section 9 and 10 of SKILL.md). Weather is attached to the response as warnings. If risk ever has to steer routes, add per-season cost columns, not a runtime term.

## 5. Profile `astronaut`

Hard limit: slope > 15 deg (config; unconfirmed).

Parameters: `body_mass_kg`, `suit_mass_kg`, `gear_mass_kg` (`m_total` = sum), `efficiency_factor` (default 1.0), `suit_mobility_penalty` (>= 1.0, empirical), `speed_factor`, `gravity_factor` (calibration for 3.71 m/s2, default 1.0), `P_suit_W`, `o2_leak_g_per_s`, `env_heat_W`, `rq` (~0.85), `o2_kJ_per_L` (~20.1), `h_cool_J_per_g`. No real values yet.

```
v(i)   = speed_factor * 6 * exp(-3.5 * |i + 0.05|) km/h                (Tobler 1993, converted to m/s)
C(i)   = 280.5 i^5 - 58.7 i^4 - 76.8 i^3 + 51.9 i^2 + 19.6 i + 2.5     (Minetti et al. 2002, J/(kg*m), valid |i| <= 0.45)
e(i)   = C(i) * m_total * efficiency_factor * suit_mobility_penalty * gravity_factor      (J/m)
t      = L / v(i)
E_met  = e(i) * L                                                      (J, metabolic)
o2_g   = E_met / (o2_kJ_per_L * 1000) * 1.429  +  o2_leak_g_per_s * t
co2_g  = rq * E_met / (o2_kJ_per_L * 1000) * 1.977
water_g= (E_met + env_heat_W * t) / h_cool_J_per_g
energy_wh = P_suit_W * t / 3600
```

Notes:
- 1.429 g/L (O2) and 1.977 g/L (CO2) are densities at 0 C, 1 atm.
- Check whether Minetti's figure is a net or gross cost; if net, add a resting baseline to `o2_g` and `water_g`.
- Mars gravity lowers the real cost, but the scaling is approximate; `gravity_factor` is a calibration knob, not physics.
- Oxygen, CO2 removal and cooling water all scale with `E_met`, so they are nearly collinear; keep them separate because their capacities differ. The binding limit is whichever capacity is smallest relative to its use.
- Who the astronaut is enters mainly through mass: Minetti gives energy per kg per metre, so `m_total` (body + suit + gear) scales it. **Mass cancels in the route cost** (`e(i)/e_flat` has it in both parts), so every astronaut gets the same route; it only scales `o2_g`, `co2_g` and `water_g`. Those three are therefore recomputed per request for the requesting user's body mass, over the edges of the returned path (`AstronautModel.resources(geom, body_mass_kg)`, shared with the graph builder, which uses the reference `body_mass_kg`); the stored graph columns are the reference-mass values. Optional parameter `max_metabolic_rate_W` (a fraction of aerobic capacity) can cap speed on climbs so the energy rate stays sustainable. Height, age and sex are not modelled (no data to calibrate them).
- Minetti's coefficients come from healthy adults on Earth without suits, so results are good for comparing routes, not for medical prediction. In reduced gravity, carried load costs closer to weight (mass x 3.71) than mass, while inertia stays tied to mass; the scaling is approximate. If suit mass dominates, the Pandolf load-carriage equation is an alternative to scaling Minetti linearly.
- A pulse oximeter does not measure consumption (SpO2 is not supply). Heart rate could later calibrate `efficiency_factor`. Out of MVP scope.

## 6. Profile `car`

Hard limit: slope > 35 deg (config; unconfirmed).

Parameters: `mass_kg`, `c_rr` (rolling resistance on regolith), `eta_drive`, `v_max`, `v_min`, `p_speed`, `P_aux_W`, `crew_n`, per-person rates `crew_o2_g_per_s`, `crew_co2_g_per_s`, `crew_water_g_per_s` (seated, pressurised cabin assumed), `g = 3.71`.

```
v(theta) = max(v_min, v_max * (1 - (|theta| / theta_max)^p_speed))
t        = L / v
F        = mass_kg * g * (c_rr * cos(theta) + sin(theta))             (signed theta: downhill reduces F)
E_trac   = max(0, F * L / eta_drive)                                  (J; no regeneration credit in the MVP)
e(i)     = E_trac / L ;   e_flat = mass_kg * g * c_rr / eta_drive
energy_wh= (E_trac + P_aux_W * t) / 3600
o2_g, co2_g, water_g = crew_n * rate * t                              (time-driven)
```

## 7. How routing uses it

- The matrix and solver use `cost` only (SKILL.md steps 4-5).
- After solving, each leg's resources are summed over its edges: `attrs[profile][attr][edge_id]` for each consecutive node pair, with `edge_id = routing_graph.edge_id(a, b)`. Report per-leg and total resources in the response.
- Compare totals with capacities from config (`o2_g`, `co2_g`, `water_g`, `energy_wh`, `time_s`) and add a warning per exceeded budget, with a reserve margin (config, e.g. 20 %). MVP does not enforce budgets inside the search.
- Future (not MVP): walk-back feasibility. Run Dijkstra backwards from the habitat to get a per-node return cost for each resource, then keep a node only if `outbound + return <= capacity * (1 - reserve)`. A car trip must also stay within walking range of the habitat using the astronaut resources. Needs a habitat location in the request or config.

## 8. Configuration

Everything below lives in **`config/mars.yaml`** (override the file with `MARS_CONFIG` for the API or `--config` for `python -m app.graph`). It is read by `app/core/configfile/` into `Settings` and validated at startup; a typo, a wrong type or an inconsistent value stops the program with a message naming the key.

| Section | What it holds |
|---|---|
| `profiles.<astronaut\|car>` | every model parameter: `hard_limit_deg`, `alpha`, `beta`, `p` and the parameters of sections 5 and 6 (names match `AstronautParams` / `CarParams`). A parameter that is not listed keeps the default in `app/routing/profiles/params.py`. |
| `capacities.<profile>` | budgets the vehicle or suit carries, per resource (`time_s`, `o2_g`, `co2_g`, `water_g`, `energy_wh`); empty = no budget warnings |
| `routing` | `reserve_margin` (share of each budget kept in reserve), `max_snap_distance_m` |
| `slope_classes` | classes of the map overlay (display only); the loader checks that the steepest walkable class ends at the astronaut `hard_limit_deg` and the steepest drivable class at the car limit |
| `grid`, `poi` | `grid.coarsen` (1 = native 200 m), `poi.sample_radius_km` |
| `confirmation` | per section `status: placeholder\|confirmed` and a `source`; a confirmed section must name its source, and the API logs the unconfirmed sections at startup |

Changing a profile parameter changes the graph's `formula_version`, so the saved graph is stale: rebuild it with `python -m app.graph`. Until then the API keeps the reference-mass numbers and warns (section 5, body mass).

## 9. Tests

`compute_edge_attrs(profile, geom, params) -> dict[str, ndarray]` is a pure, vectorised function; test it without any graph or data:
- Flat edge: `cost == L` when `alpha + beta == 1`.
- Uphill: cost and energy increase with gradient. Gentle downhill is cheaper than flat for the astronaut; steep downhill costs more than gentle downhill (Minetti minimum near i = -0.2).
- Beyond the hard limit: all attributes `inf`. Elsewhere: all >= 0, no NaN.
- A->B and B->A differ on a slope.
- Resources scale linearly with `L` on a uniform slope.
- Location: `backend/tests/routing/` (or `backend/tests/profiles/`), per the development rules (SKILL.md section 11).

## 10. Constraint catalogue, alternatives and deferred items

What an EVA is limited by, and how each item is handled:

| Constraint | Driven by | MVP handling |
|---|---|---|
| Oxygen | metabolic energy plus leakage over time | edge attribute `o2_g`, budget warning |
| CO2 removal (scrubber load) | metabolic energy (CO2 output tracks O2 use) | edge attribute `co2_g`, budget warning |
| Cooling water | heat to reject: metabolic heat plus environment | edge attribute `water_g` (environment load is a config constant, no data) |
| Drinking water, electrolytes | sweat loss (metabolic rate, time) | informational only; rarely limits a 6-8 h EVA |
| Battery / energy | time (suit draw), traction (car) | edge attribute `energy_wh`, budget warning |
| EVA duration | operational limit, typically 6-8 h (config) | sum of `time_s` against `capacities.<profile>.time_s` |
| Walk-back | return trip must fit the remaining resources (Apollo-style rule) | future filter, section 7 |
| Radiation | chronic dose = rate x time; solar particle events (SPE) are the real hazard | not modelled. Planned as an SPE shelter-reachability rule (needs a "distance to shelter" node attribute), not a dose calculation. Deep terrain may be partly shielded by atmosphere depth and canyon walls (the DEM could proxy this), but that needs a real source before use |
| Thermal environment, communications line of sight, rock abundance | sun/shadow, terrain, surface | not modelled: no data in our datasets. DEM roughness is a coarse proxy at 200 m |
| Dust-storm risk | season, location | not in the cost (see section 4); shown as a warning from the weather frame, rendered verbatim |

Design notes:
- **No standard formula exists.** The established pattern is a weighted sum of normalised criteria plus hard constraints. Tobler (speed) and Minetti (energy) are the established sub-models. Weights express mission priorities, so they come from the product owner, not from a source.
- **Alternatives:** a Pareto set (several non-dominated routes), or minimise time subject to energy and risk caps. The weighted sum is the simplest for an MVP.
- **Why resources are constraints, not weights:** oxygen, battery and time are hard budgets. Keep the objective a simple weighted `cost` and enforce budgets as feasibility, rather than trading them off.
- **Walk-back detail (future):** one backward Dijkstra from the habitat gives a per-node return cost per resource. Separate minima per resource are optimistic (they may not be achievable on one path); pick one return path (minimise O2, the critical resource) and check every resource along it. A car trip must also stay within walking range of the habitat using the astronaut resources.
- **Pulse oximeter:** SpO2 is blood saturation, not consumption or remaining supply, so it cannot feed the oxygen budget (in a suit with supplied oxygen it stays normal until something fails). Heart rate is roughly linear with oxygen consumption per individual, so it could calibrate `efficiency_factor` per astronaut, or drive live budget updates and re-planning. Low SpO2 could be a safety alert. All out of MVP scope: the app is a static planning tool with no live telemetry.
