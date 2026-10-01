const test=require('node:test'),assert=require('node:assert/strict'),LabQC=require('./manual_qc.js');
function fixture(initial='median'){
 const columns=['field','segmentation_channel','object_id','region','measurement_channel','area_pixels','raw_mean','raw_sum','background_median','corrected_mean','corrected_sum'];
 const fields={};for(const[f,med,mean]of [['f0',10,30],['f1',20,35]])fields[f]={background:{valid:true,medians:{A:med,B:5},means:{A:mean,B:9}},objects:{S:[{id:1}]}};
 const rows=[['f0','S','1','whole','A','2','25','50','10','15','30'],['f0','S','1','whole','B','2','25','50','5','20','40'],['f1','S','1','whole','A','2','40','80','20','20','40'],['f0','S','1','interior','A','','','','10','','']];
 const bundle={columns,rows,dataset_id:'test',source_csv_sha256:'csv',source_viewer_sha256:'viewer',background_estimator:initial};
 return {bundle,fields,qc:LabQC.create(bundle,fields)};
}
test('per-channel choice applies to every FOV and leaves immutable raw data intact',()=>{
 const {bundle,fields,qc}=fixture(),before=JSON.stringify({bundle,fields});
 qc.setEstimator('A','mean');assert.equal(qc.estimator('B'),'median');
 const m=qc.measurement('f0','A',{mean:25,sum:50},2);assert.equal(m.corrected,-5);assert.equal(m.correctedSum,-10);
 assert.equal(qc.measurement('f1','A',{mean:40,sum:80},2).corrected,5);
 assert.equal(qc.measurement('f0','B',{mean:25,sum:50},2).corrected,20);
 assert.equal(JSON.stringify({bundle,fields}),before);
 const csv=qc.includedCSV('all');assert.match(csv,/"background_mean","background_estimator","background_value"/);
 assert.ok(csv.includes('"25","50","10","-5","-10","30","mean","30"'));
 assert.ok(csv.includes('"40","80","20","5","10","35","mean","35"'));
 assert.ok(csv.includes('"interior","A","","","","10","","","30","mean","30"'));
 qc.setEstimator('A','median');assert.equal(qc.measurement('f0','A',{mean:25,sum:50},2).corrected,15);
});
test('QC JSON round-trip, imported old state, undo and exclusions preserve the selected method',()=>{
 const {qc}=fixture();qc.setEstimator('A','mean');qc.toggle('f0','S',1);
 const restored=fixture().qc;restored.load(JSON.parse(JSON.stringify(qc.snapshot())));
 assert.equal(restored.estimator('A'),'mean');assert.equal(restored.excludedCount(),1);
 assert.ok(!restored.includedCSV('all').includes('"f0"'));
 qc.undoLast();assert.equal(qc.excludedCount(),0);assert.equal(qc.estimator('A'),'mean');
 qc.undoLast();assert.equal(qc.estimator('A'),'median');
 qc.importState(restored.snapshot());assert.equal(qc.estimator('A'),'mean');assert.equal(qc.excludedCount(),1);
 const old=qc.snapshot();delete old.background_estimators;qc.load(old);assert.equal(qc.estimator('A'),'median');
});
test('mean defaults, invalid BG, missing statistics and malformed imports fail without silent substitution',()=>{
 const {fields,bundle}=fixture('mean');let qc=LabQC.create(bundle,fields);assert.equal(qc.estimator('A'),'mean');
 fields.f0.background.valid=false;assert.equal(qc.measurement('f0','A',{mean:25,sum:50},2).corrected,null);
 delete fields.f1.background.means;qc=LabQC.create({...bundle,background_estimator:'median'},fields);
 assert.equal(qc.canUseEstimator('A','mean'),false);const before=JSON.stringify(qc.snapshot());
 for(const settings of [{A:'mean'},{A:'auto'},{Z:'median'},[],false]){
  assert.throws(()=>qc.load({...qc.snapshot(),background_estimators:settings}));assert.equal(JSON.stringify(qc.snapshot()),before);
 }
 assert.throws(()=>qc.setEstimator('A','mean'));assert.equal(qc.estimator('A'),'median');
 assert.equal(qc.measurement('f1','A',{mean:40,sum:80,background:20},2).corrected,20);
});
test('method mutations obey revision limits and do not lose previous settings or undo',()=>{
 const {qc}=fixture();const state=qc.snapshot();state.revision=Number.MAX_SAFE_INTEGER;qc.load(state);
 const before=JSON.stringify(qc.snapshot());assert.throws(()=>qc.setEstimator('A','mean'),/limit/);assert.equal(JSON.stringify(qc.snapshot()),before);
});
