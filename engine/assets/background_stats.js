/* Recompute corrections from immutable raw measurements and saved background stats. */
(function(root){
'use strict';
function create(bundle,fields){
 const ix=Object.fromEntries(bundle.columns.map((c,i)=>[c,i]));
 const channels=[...new Set(bundle.rows.map(r=>r[ix.measurement_channel]).filter(x=>typeof x==='string'))];
 const initial=bundle.background_estimator||'median';
 if(!['median','mean'].includes(initial))throw Error('Invalid saved background estimator');
 const enabled=['raw_mean','raw_sum','area_pixels','background_median','corrected_mean','corrected_sum'].every(k=>ix[k]!==undefined);
 const num=x=>x!==''&&x!=null&&Number.isFinite(Number(x))?Number(x):null;
 function available(channel,method){
  if(!channels.includes(channel)||!['median','mean'].includes(method))return false;
  if(method==='median')return true;
  return Object.values(fields).every(f=>f.background?.means&&Object.hasOwn(f.background.means,channel)&&
   (Number.isFinite(f.background.means[channel])||(f.background.valid===false&&f.background.means[channel]===null)));
 }
 function validate(settings={}){
  if(!settings||typeof settings!=='object'||Array.isArray(settings))throw Error('Invalid background settings');
  for(const [channel,method]of Object.entries(settings))if(!available(channel,method))throw Error('Background method is unavailable for this channel or saved result');
  return {...settings};
 }
 function method(settings,channel){return settings[channel]||initial;}
 function measurement(field,channel,m,area,settings){
  if(!m)return undefined;
  const f=fields[field],estimator=method(settings,channel),stats=f.background||{};
  const median=stats.medians?.[channel]??m.backgroundMedian??((m.backgroundEstimator||initial)==='median'?m.background:null);
  const mean=stats.means?.[channel]??m.backgroundMean??null;
  const value=estimator==='mean'?mean:median;
  const valid=stats.valid===true&&Number.isFinite(value)&&Number.isFinite(area)&&area>0;
  return {...m,background:value,backgroundMedian:median,backgroundMean:mean,backgroundEstimator:estimator,
   corrected:valid&&Number.isFinite(m.mean)?m.mean-value:null,
   correctedSum:valid&&Number.isFinite(m.sum)?m.sum-area*value:null};
 }
 const additions=['background_mean','background_estimator','background_value'];
 const columns=enabled?[...bundle.columns,...additions.filter(k=>ix[k]===undefined)]:bundle.columns;
 function exportRow(row,settings){
  if(!enabled)return row;
  const m=measurement(row[ix.field],row[ix.measurement_channel],{
   mean:num(row[ix.raw_mean]),sum:num(row[ix.raw_sum]),background:num(row[ix.background_value]??row[ix.background_median]),
   backgroundMedian:num(row[ix.background_median]),backgroundMean:num(row[ix.background_mean]),backgroundEstimator:row[ix.background_estimator]||initial
  },num(row[ix.area_pixels]),settings);
  const values={background_median:m.backgroundMedian,background_mean:m.backgroundMean,background_estimator:m.backgroundEstimator,background_value:m.background,corrected_mean:m.corrected,corrected_sum:m.correctedSum};
  return columns.map(k=>Object.hasOwn(values,k)?values[k]:row[ix[k]]);
 }
 return {available,validate,method,measurement,exportRow,columns,initial};
}
const api={create};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LabBackground=api;
})(globalThis);
