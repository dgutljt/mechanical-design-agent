// Unregistered future-entry transport checks and safe presentation helpers.
import { CONTRACT_VERSION } from './torque.js';
import { OPERATION, MAX_LOAD_RECORDS, encodeSignedZeroJson, snapshotJsonData } from './overhung-input.js';

const TORQUE = 'transmitted_torque_v1';
const STATICS = 'two_support_overhung_two_plane_point_load_v1';
const PLANE = 'two_support_overhung_signed_point_load_v1';
const COMBINED = 'solid_shaft_combined_tresca_v1';
const COORDINATE = '+x A-to-B; plane_1 loads along +y, plane_2 loads along +z; plane_1_moment is M_z, plane_2_moment is -M_y; each signed scalar follows dM/dx=V on shaft domain [-a,L+b]';
const SIGN = '+x A-to-B; +q is the chosen transverse direction; forces/reactions positive +q; V=sum(left external forces); dM/dx=V; plane 1 +q=+y gives M_z=M; plane 2 +q=+z gives M_y=-M';
const CRITERION = 'maximum shear stress (Tresca)';
function bad(message = 'Invalid overhung response structure or lineage'): never { throw Error(message); }
function requireValue(condition: boolean) { if (!condition) bad(); }
const finite = (v: any) => typeof v === 'number' && Number.isFinite(v);
const nonnegative = (v: any) => finite(v) && v >= 0;
const positive = (v: any) => finite(v) && v > 0;
const text = (v: any) => typeof v === 'string' && v.trim().length > 0;
const literal = (expected: any) => (v: any) => Object.is(v, expected);
function same(a: any, b: any): boolean {
  if (typeof a !== typeof b) return false;
  if (!a || typeof a !== 'object') return Object.is(a, b);
  if (!b || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(k => Object.hasOwn(b, k) && same(a[k], b[k]));
}
const exact = (expected: any) => (v: any) => same(v, expected);
function object(required: Record<string, (v: any) => boolean>, optional: Record<string, (v: any) => boolean> = {}) {
  return (v: any): boolean => !!v && typeof v === 'object' && !Array.isArray(v) &&
    Object.keys(required).every(k => Object.hasOwn(v, k) && required[k](v[k])) &&
    Object.keys(v).every(k => Object.hasOwn(required, k) || Object.hasOwn(optional, k) && optional[k](v[k]));
}
const array = (item: (v: any) => boolean, min = 0) => (v: any) => Array.isArray(v) && v.length >= min && v.every(item);
const texts = array(text, 1);
const units = object({ force: literal('N'), position: literal('mm'), moment: literal('N*mm'), converted_moment: literal('N*m') });
const geometry = { support_span_mm: positive, left_overhang_mm: nonnegative, right_overhang_mm: nonnegative };
const region = object({ x_start_mm: finite, x_end_mm: finite });
const station = object({ position_mm: finite, plane_1_moment_nmm: finite,
  plane_2_moment_nmm: finite, resultant_bending_moment_nmm: nonnegative });
const regions = array(region, 1), stations = array(station, 1);
const load = object({ load_n: finite, position_mm: finite });
const plane = object({ model_id: literal(PLANE), ...geometry, loads: array(load),
  total_load_n: finite, reaction_a_n: finite, reaction_b_n: finite,
  stations: array(object({ position_mm: finite, moment_nmm: finite }), 2),
  segments: array(object({ x_start_mm: finite, x_end_mm: finite, shear_n: finite,
    moment_start_nmm: finite, moment_end_nmm: finite }), 1),
  signed_max_bending_moment_nmm: finite, signed_min_bending_moment_nmm: finite,
  critical_bending_moment_nmm: nonnegative, critical_bending_moment_nm: nonnegative,
  critical_moment_regions: regions, sign_convention: literal(SIGN), units,
  formula: literal('RA+RB+sum(Fi)=0; RB*L+sum(Fi*xi)=0; V=sum(left external forces); M=sum(left force*(x-force position))'), assumptions: texts });
const statics = object({ model_id: literal(STATICS), ...geometry, plane_1: plane, plane_2: plane,
  common_stations_mm: array(finite, 2), resultant_stations: stations,
  critical_resultant_bending_moment_nmm: nonnegative, critical_resultant_bending_moment_nm: nonnegative,
  critical_stations: stations, critical_regions: regions, coordinate_convention: literal(COORDINATE), units,
  formula: literal('M_z=m1; M_y=-m2; R(x)=hypot(m1(x),m2(x)); critical=max(R(common events))'), assumptions: texts });
const torque = object({ model_id: literal(TORQUE), power_kw: nonnegative, speed_rpm: positive,
  torque_nm: nonnegative, constant: literal(9550), formula: literal('T = 9550 * P / n') });
const combined = object({ model_id: literal(COMBINED), bending_moment_nm: nonnegative,
  bending_moment_nmm: nonnegative, torque_nm: nonnegative, torque_nmm: nonnegative,
  allowable_shear_mpa: positive, combined_load_term_nmm: nonnegative, min_diameter_mm: nonnegative,
  criterion: literal(CRITERION), formula: literal('d_min = (16 * sqrt(M_Nmm^2 + T_Nmm^2) / (pi * tau_allow))^(1/3)'), assumptions: texts });
const review = (state: (v: any) => boolean) => object({ torque: state, statics: state, combined: state });
const transfer = (model: string, field: string) => object({ source_model_id: literal(model), source_field: literal(field),
  source_unit: literal('N*m'), exact_value: nonnegative });
const nested = (field: string, component: string) => object({ source_model_id: literal(PLANE), parent_model_id: literal(STATICS),
  result_field: literal('statics.' + field), component: literal(component) });
const lineage = object({ torque: transfer(TORQUE, 'torque_nm'), bending_moment: transfer(STATICS, 'critical_resultant_bending_moment_nm'),
  critical_stations: stations, critical_regions: regions, coordinate_convention: literal(COORDINATE),
  nested_plane_models: object({ plane_1: nested('plane_1', 'M_z'), plane_2: nested('plane_2', '-M_y') }) });

// Fixed identities and public units from the already accepted registry contract.
// These mappings do not calculate mechanics or change Registry/Reviewer behavior.
const MODEL_MAP: Record<string, any> = {
  [TORQUE]: { module: 'torque', fn: 'calculate_transmitted_torque', skill: 'transmission-torque',
    source: 'oer_strength_materials_torsion', output: 'torque_nm',
    inputs: ['power_kw', 'speed_rpm'], units: ['P_kW: kW', 'n_rpm: revolutions per minute', 'T_Nm: N*m'] },
  [STATICS]: { module: 'shaft_statics_overhung_two_plane', fn: 'calculate_two_support_overhung_two_plane_point_loads',
    skill: 'shaft-multi-point-load-statics', source: 'engineering_statics_beam_equilibrium',
    coordinate: '+x A-to-B; plane_1 +y; plane_2 +z; M_z=m1; M_y=-m2',
    units: ['forces and reactions: N', 'positions: mm', 'component and resultant moments: N*mm', 'converted critical resultant: N*m'] },
  [PLANE]: { module: 'shaft_statics_overhung', fn: 'calculate_two_support_overhung_signed_point_loads',
    skill: 'shaft-multi-point-load-statics', source: 'engineering_statics_beam_equilibrium',
    sign: '+x A-to-B; +q transverse; plane 1 +q=+y and M_z=M; plane 2 +q=+z and M_y=-M',
    units: ['forces and reactions: N', 'positions: mm', 'moments: N*mm', 'converted critical moment: N*m'] },
  [COMBINED]: { module: 'shaft_combined', fn: 'calculate_solid_shaft_min_diameter_combined', skill: 'combined-shaft-loading',
    source: 'air_force_stress_manual_shafting', output: 'min_diameter_mm',
    inputs: ['bending_moment_nm', 'torque_nm', 'allowable_shear_mpa'],
    units: ['M and T inputs: N*m', 'M and T internal: N*mm (inputs multiplied by 1000)', 'sigma, tau, and tau_allow: MPa = N/mm^2', 'd: mm'] }
};
const SOURCE_MAP: Record<string, any> = {
  oer_strength_materials_torsion: { url: 'https://jrgrohs.github.io/StrengthofMaterials/Chapter%206.html', year: 2025 },
  engineering_statics_beam_equilibrium: { url: 'https://engineeringstatics.org/' },
  air_force_stress_manual_shafting: { url: 'https://engineeringlibrary.org/reference/shaft-analysis-air-force-stress-manual', year: 1986 }
};
function provenance(v: any): boolean {
  const entries: Record<string, (v: any) => boolean> = {};
  for (const [id, spec] of Object.entries(MODEL_MAP)) {
    const fields: Record<string, (v: any) => boolean> = {
      model_id: literal(id), title: text, status: literal('validated calculator model'),
      calculator_module: literal('mechanical_agent.calculators.' + spec.module), calculator_function: literal(spec.fn),
      dsh_skill: literal(spec.skill), purpose: text, equation: text, derivation: text,
      inputs: spec.inputs ? exact(spec.inputs) : texts, units: exact(spec.units),
      assumptions: texts, limitations: texts, source_ids: exact([spec.source])
    };
    if (spec.output) fields.output = literal(spec.output); else fields.outputs = texts;
    if (spec.coordinate) fields.coordinate_convention = literal(spec.coordinate);
    if (spec.sign) fields.sign_convention = literal(spec.sign);
    if (id === COMBINED) fields.criterion = literal(CRITERION);
    const sourceSpec = SOURCE_MAP[spec.source];
    const sourceFields: Record<string, (v: any) => boolean> = {
      id: literal(spec.source), title: text, organization_or_author: text, source_type: text, host: text,
      section: text, url: literal(sourceSpec.url), supports: texts, notes: text
    };
    if (sourceSpec.year !== undefined) sourceFields.year = literal(sourceSpec.year);
    entries[id] = object({ model: object(fields), sources: (s: any) => Array.isArray(s) && s.length === 1 && object(sourceFields)(s[0]) });
  }
  return object(entries)(v);
}

// P1A Adapter exposes no public metadata fields. Empty object is the exact
// whitelist; environment, paths, test data and future fields are rejected.
const metadata = object({});
const success = object({ contract_version: literal(CONTRACT_VERSION), operation: literal(OPERATION), ok: literal(true),
  workflow_id: literal(OPERATION), status: literal('PASS'), reviews: review(literal('PASS')),
  results: object({ torque, statics, combined }), lineage, provenance, assume_constant_torque_over_shaft: literal(true),
  assumptions: texts, limitations: texts, metadata });
const SAFE_ERRORS: Record<string, string> = {
  INVALID_TOOL_INPUT: 'Invalid engineering request.', PYTHON_RESOLUTION_ERROR: 'Compatible interpreter unavailable.',
  PYTHON_PROCESS_ERROR: 'Engineering process failed.', ENGINEERING_INPUT_ERROR: 'Engineering input rejected.',
  CALCULATOR_ERROR: 'Engineering calculation failed.', REVIEW_FAIL: 'Engineering review rejected the result.',
  REQUEST_BINDING_ERROR: 'Engineering request binding failed.', PROVENANCE_ERROR: 'Engineering provenance failed.',
  LINEAGE_ERROR: 'Engineering lineage failed.', INTERNAL_ADAPTER_ERROR: 'Engineering adapter failed.',
  TIMEOUT: 'Engineering operation timed out.', CANCELLED: 'Engineering operation cancelled.'
};
const failure = object({ contract_version: literal(CONTRACT_VERSION), operation: literal(OPERATION), ok: literal(false),
  error: object({ code: (v: any) => typeof v === 'string' && Object.hasOwn(SAFE_ERRORS, v), message: text }), metadata },
  { workflow_id: literal(OPERATION), status: literal('FAIL'), reviews: review((v: any) => ['PASS', 'FAIL', 'NOT_RUN'].includes(v)) });

function checkRelationships(value: any) {
  const r = value.results, s = r.statics, l = value.lineage;
  requireValue(Object.is(l.torque.exact_value, r.torque.torque_nm) && Object.is(r.combined.torque_nm, r.torque.torque_nm));
  requireValue(Object.is(l.bending_moment.exact_value, s.critical_resultant_bending_moment_nm) &&
    Object.is(r.combined.bending_moment_nm, s.critical_resultant_bending_moment_nm));
  requireValue(same(l.critical_stations, s.critical_stations) && same(l.critical_regions, s.critical_regions));
  const end = s.support_span_mm + s.right_overhang_mm;
  requireValue((s.left_overhang_mm > 0 || s.right_overhang_mm > 0) && Number.isFinite(end) && Number.isFinite(s.left_overhang_mm + end));
  const inDomain = (x: number) => x >= -s.left_overhang_mm && x <= end;
  const ordered = (xs: number[]) => xs.every((x, i) => inDomain(x) && (i === 0 || x > xs[i - 1]));
  const boundedRegions = (rs: any[]) => rs.every(region => inDomain(region.x_start_mm) && inDomain(region.x_end_mm) && region.x_start_mm <= region.x_end_mm);
  requireValue(ordered(s.common_stations_mm) && s.resultant_stations.length === s.common_stations_mm.length);
  requireValue(s.resultant_stations.every((station: any, i: number) => Object.is(station.position_mm, s.common_stations_mm[i])));
  requireValue(ordered(s.critical_stations.map((station: any) => station.position_mm)) && boundedRegions(s.critical_regions));
  requireValue(s.critical_stations.every((station: any) => s.resultant_stations.some((source: any) => same(source, station))));
  requireValue(s.plane_1.loads.length + s.plane_2.loads.length <= MAX_LOAD_RECORDS);
  for (const field of ['plane_1', 'plane_2']) {
    const p = s[field];
    requireValue(Object.keys(geometry).every(k => Object.is(p[k], s[k])));
    requireValue(p.loads.length <= MAX_LOAD_RECORDS && p.loads.every((load: any) => inDomain(load.position_mm)));
    requireValue(ordered(p.stations.map((station: any) => station.position_mm)) && boundedRegions(p.critical_moment_regions));
    requireValue(p.segments.length === p.stations.length - 1);
    requireValue(p.segments.every((segment: any, i: number) => Object.is(segment.x_start_mm, p.stations[i].position_mm) &&
      Object.is(segment.x_end_mm, p.stations[i + 1].position_mm) &&
      Object.is(segment.moment_start_nmm, p.stations[i].moment_nmm) && Object.is(segment.moment_end_nmm, p.stations[i + 1].moment_nmm)));
    // Model/result/lineage identities are exact in the schemas above. Both
    // nested planes refer to the SAME required single-plane provenance card.
    requireValue(l.nested_plane_models[field].source_model_id === p.model_id &&
      l.nested_plane_models[field].parent_model_id === s.model_id);
  }
  requireValue(same(value.provenance[PLANE].sources, value.provenance[STATICS].sources));
}

// Complete structure and copied-data relationships only. No force equilibrium,
// bending, torque or diameter equations are recomputed; Python Reviewer owns them.
// Return the validated PRIVATE snapshot so consumers never render caller objects.
export function validateOverhungResponse(value: any) {
  let snapshot;
  try { snapshot = snapshotJsonData(value); } catch { bad('Invalid overhung response data'); }
  if (snapshot?.ok === false) {
    if (!failure(snapshot)) bad('Invalid failure envelope');
    const workflowFields = ['workflow_id', 'status', 'reviews'].filter(k => Object.hasOwn(snapshot, k));
    if (workflowFields.length !== 0 && workflowFields.length !== 3) bad('Invalid failure envelope');
    // Never return or render the Adapter's raw diagnostic text. Even a legitimate
    // error code may accompany a traceback/path/environment string.
    return snapshotJsonData({ ...snapshot, error: { code: snapshot.error.code, message: SAFE_ERRORS[snapshot.error.code] } });
  }
  if (!success(snapshot)) bad();
  checkRelationships(snapshot);
  return snapshot;
}

export function decodeOverhungResponse(payload: string) {
  if (typeof payload !== 'string') bad('Invalid overhung response JSON');
  let value;
  try { value = JSON.parse(payload); } catch { bad('Invalid overhung response JSON'); }
  return validateOverhungResponse(value);
}
export function renderOverhungResponse(value: any) {
  const safe = validateOverhungResponse(value);
  return [{ type: 'text', text: encodeSignedZeroJson(safe) }];
}
