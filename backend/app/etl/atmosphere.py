"""Grid-cell thermodynamics for verified EAC4 IFS L60 fields, never province means.

IFS archived tracers are specific ratios relative to total/moist air (ECMWF
Technical Memorandum 849, section 2.6). The transport-conservation caveat is
recorded separately; no EGG4 dry-air interpretation is silently applied.
The ideal gaseous mixture neglects condensed water, explicitly in provenance.
"""
import json
from pathlib import Path
import numpy as np

R_D = 287.05
R_V = 461.5
METHOD_VERSION = 'eac4-l60-moist-density-v1'
MMR_BASIS = 'moist_air'
MMR_REFERENCE = 'https://www.ecmwf.int/sites/default/files/elibrary/2019/19114-dry-mass-versus-total-mass-conservation-ifs.pdf'
L60_REFERENCE = json.loads((Path(__file__).parent / 'fixtures/eac4_l60.json').read_text())

# Bit masks retain all failures without per-cell Python strings or clipping.
MISSING_T, INVALID_T, MISSING_Q, INVALID_Q = 1, 2, 4, 8
MISSING_P, INVALID_P, MISSING_MMR, INVALID_MMR = 16, 32, 64, 128
INVALID_RHO = 256
REASONS = {INVALID_RHO: 'invalid_air_density',MISSING_T:'missing_model_temperature', INVALID_T:'invalid_model_temperature',
           MISSING_Q:'missing_model_specific_humidity', INVALID_Q:'invalid_model_specific_humidity',
           MISSING_P:'missing_model_pressure', INVALID_P:'invalid_model_pressure',
           MISSING_MMR:'missing_gas_mixing_ratio', INVALID_MMR:'negative_gas_mixing_ratio'}


def reason_text(flags):
    return '|'.join(text for bit,text in REASONS.items() if int(flags) & bit)


class HybridCoordinate:
    def __init__(self, pv, level):
        self.pv = np.asarray(pv, dtype=float)
        # PV = A[0..N] followed by B[0..N]; full level k uses k-1 and k.
        if self.pv.shape != (122,) or not np.all(np.isfinite(self.pv)):
            raise ValueError('Exact EAC4 L60 PV coefficients are required')
        if not any(np.array_equal(self.pv, variant) for variant in L60_REFERENCE['pv_variants']):
            raise ValueError('PV does not match the verified ECMWF L60 configuration')
        if not isinstance(level, (int, np.integer)) or not 1 <= level <= 60:
            raise ValueError('Invalid EAC4 model level')
        self.level = int(level)
        self.a, self.b = self.pv[:61], self.pv[61:]
        if self.a[-1] != 0 or self.b[-1] != 1:
            raise ValueError('Invalid surface pressure boundary')

    def pressure(self, surface_pressure, *, unit='Pa', param_id=134):
        if unit != 'Pa' or param_id != 134:
            raise ValueError('Pressure requires surface pressure paramId 134 in Pa, never MSLP/hPa')
        sp = np.asarray(surface_pressure, dtype=float)
        above = self.a[self.level-1] + self.b[self.level-1]*sp
        below = self.a[self.level] + self.b[self.level]*sp
        valid = np.isfinite(sp) & (sp > 0) & (above >= 0) & (below > above) & (below <= sp * (1+1e-12))
        return np.where(valid, (above+below)/2, np.nan), above, below


def moist_air_density(pressure, temperature, humidity, *, pressure_unit='Pa', temperature_unit='K', humidity_unit='kg kg**-1'):
    if (pressure_unit,temperature_unit,humidity_unit) != ('Pa','K','kg kg**-1'):
        raise ValueError('Density requires Pa, Kelvin and model-level specific humidity kg/kg')
    p,t,q = np.broadcast_arrays(np.asarray(pressure,float),np.asarray(temperature,float),np.asarray(humidity,float))
    flags = np.zeros(p.shape, dtype=np.uint16)
    for values, missing, invalid, bad in [(p,MISSING_P,INVALID_P,p<=0),(t,MISSING_T,INVALID_T,t<=0),(q,MISSING_Q,INVALID_Q,(q<0)|(q>=1))]:
        flags[~np.isfinite(values)] |= missing
        flags[np.isfinite(values)&bad] |= invalid
    gas_constant = (1-q)*R_D + q*R_V
    valid = flags == 0
    density = np.full(p.shape,np.nan)
    np.divide(p,gas_constant*t,out=density,where=valid)
    bad_density = valid & (~np.isfinite(density)|(density<=0))
    flags[bad_density] |= INVALID_RHO
    density[flags!=0] = np.nan
    return density,flags


def gas_concentration(mmr, density, humidity, *, basis, target_unit, source_unit='kg kg**-1', flags=None):
    if source_unit != 'kg kg**-1' or basis not in ('moist_air','dry_air'):
        raise ValueError('A verified mixing-ratio unit and mass basis are required')
    if target_unit not in ('µg/m³','mg/m³'):
        raise ValueError('Unsupported gas concentration unit')
    mmr,rho,q = np.broadcast_arrays(np.asarray(mmr,float),np.asarray(density,float),np.asarray(humidity,float))
    flags = np.zeros(mmr.shape,np.uint16) if flags is None else np.array(flags,dtype=np.uint16,copy=True)
    flags[~np.isfinite(mmr)] |= MISSING_MMR
    flags[np.isfinite(mmr)&(mmr<0)] |= INVALID_MMR
    flags[(~np.isfinite(rho)|(rho<=0)) & (flags==0)] |= INVALID_RHO
    if basis == 'dry_air':
        flags[~np.isfinite(q)] |= MISSING_Q
        flags[np.isfinite(q)&((q<0)|(q>=1))] |= INVALID_Q
        rho = (1-q)*rho
    result = mmr*rho*(1e6 if target_unit=='mg/m³' else 1e9)
    result = np.where(flags==0,result,np.nan)
    return result,flags
