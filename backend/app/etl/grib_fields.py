"""Bounded, timestamp-aligned raw model inputs for dashboard gas conversion."""
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import numpy as np
import eccodes as ec

from app.etl.atmosphere import HybridCoordinate, moist_air_density, gas_concentration, MMR_BASIS, MISSING_P, INVALID_P


def timestamp(handle):
    date,time = ec.codes_get(handle,'validityDate'),ec.codes_get(handle,'validityTime')
    return datetime.strptime(f'{date:08d}{time:04d}','%Y%m%d%H%M').replace(tzinfo=timezone.utc)


def decode(handle):
    values = ec.codes_get_values(handle)
    if ec.codes_get(handle,'bitmapPresent'):
        values[np.asarray(ec.codes_get_array(handle,'bitmap'))==0] = np.nan
    values[~np.isfinite(values)] = np.nan
    return values


class FieldStream:
    def __init__(self, path, param_id, unit, grid_id, coordinate, grid_coordinates=None):
        self.stream = path.open('rb')
        self.param_id,self.unit,self.grid_id,self.coordinate = param_id,unit,grid_id,coordinate
        self.grid_coordinates = grid_coordinates
        self.native_grid_id = None
        self.current = None
        self.previous = None
        self._advance()

    def close(self):
        self.stream.close()

    def _advance(self):
        while (h := ec.codes_grib_new_from_file(self.stream)) is not None:
            try:
                if ec.codes_get(h,'paramId')!=self.param_id or ec.codes_get(h,'units')!=self.unit:
                    raise ValueError('Changed meteorological parameter/unit')
                current_grid=ec.codes_get(h,'md5GridSection')
                if self.native_grid_id is None:
                    if self.grid_coordinates is not None:
                        actual=(ec.codes_get_array(h,'latitudes'),ec.codes_get_array(h,'longitudes'))
                        if any(not np.array_equal(expected,found) for expected,found in zip(self.grid_coordinates,actual)):
                            raise ValueError('Different ordered grid coordinates; no implicit regridding')
                    elif current_grid!=self.grid_id:
                        raise ValueError('Different grid identities')
                    self.native_grid_id=current_grid
                if current_grid!=self.native_grid_id or ec.codes_get(h,'stepType')!='instant' or ec.codes_get(h,'dataType')!='an':
                    raise ValueError('Incompatible meteorological grid/time support')
                if self.param_id==134:
                    if ec.codes_get(h,'typeOfLevel')!='surface' or ec.codes_get(h,'level')!=0:
                        raise ValueError('Expected local surface pressure')
                else:
                    if ec.codes_get(h,'typeOfLevel')!='hybrid' or ec.codes_get(h,'level')!=self.coordinate.level:
                        raise ValueError('Temperature, humidity and gas must share a model level')
                    pv = ec.codes_get_array(h,'pv')
                    HybridCoordinate(pv,self.coordinate.level)
                instant,values=timestamp(h),decode(h)
                fingerprint=hashlib.sha256(values.tobytes()).digest()
                if self.previous:
                    if instant==self.previous[0]:
                        if fingerprint!=self.previous[1]:
                            raise ValueError('Conflicting meteorological duplicate')
                        continue
                    if instant<self.previous[0]:
                        raise ValueError('Unordered meteorological timestamps')
                self.previous=(instant,fingerprint)
                self.current=(instant,values)
                self.current_pv = pv if self.param_id != 134 else None
                return
            finally:
                ec.codes_release(h)
        self.current=None

    def at(self, instant, shape):
        while self.current is not None and self.current[0]<instant:
            self._advance()
        if self.current is None or self.current[0]!=instant:
            return np.full(shape,np.nan)
        return self.current[1]


class DensityInputs:
    def __init__(self, paths, grid_id, coordinate, grid_coordinates=None):
        self.stack=ExitStack()
        self.coordinate=coordinate
        self.sources={}
        for key,param_id,unit in [('t_model',130,'K'),('q_model',133,'kg kg**-1'),('sp',134,'Pa')]:
            if key in paths:
                field=FieldStream(paths[key],param_id,unit,grid_id,coordinate,grid_coordinates)
                self.stack.callback(field.close)
                self.sources[key]=field
        self.cached=None

    def close(self):
        self.stack.close()

    def convert(self, instant, mmr, unit, gas_pv=None):
        if self.cached is None or self.cached[0]!=instant:
            fields={key:self.sources[key].at(instant,mmr.shape) if key in self.sources else np.full(mmr.shape,np.nan)
                    for key in ('t_model','q_model','sp')}
            coordinate = HybridCoordinate(gas_pv,self.coordinate.level) if gas_pv is not None else self.coordinate
            for key in ('t_model','q_model'):
                field=self.sources.get(key)
                if field and field.current and field.current[0]==instant and not np.array_equal(field.current_pv,coordinate.pv):
                    raise ValueError('Gas and meteorology PV differ at the same timestamp')
            pressure,_,_=coordinate.pressure(fields['sp'])
            density,flags=moist_air_density(pressure,fields['t_model'],fields['q_model'])
            bad_sp = np.isfinite(fields['sp']) & (fields['sp']<=0)
            flags[bad_sp] &= np.uint16(65535 ^ MISSING_P)
            flags[bad_sp] |= INVALID_P
            self.cached=(instant,density,fields['q_model'],flags)
        _,density,humidity,flags=self.cached
        return gas_concentration(mmr,density,humidity,basis=MMR_BASIS,target_unit=unit,flags=flags)
