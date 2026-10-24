import fs from 'node:fs/promises';import path from 'node:path';
import {SpreadsheetFile,FileBlob} from '@oai/artifact-tool';
const root=path.resolve(import.meta.dirname,'..'),dir=path.join(root,'검증/v15_조서미리보기');await fs.mkdir(dir,{recursive:true});
const file=path.join(root,'배포/예시조서/통합감사_미검토초안_v1.5.xlsx');
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(file));
const records=[],views=[['조서표지','A1:B13'],['통합검토후보','A1:F3'],['통합검토후보','G1:K3'],['분석필요자료','A1:D4'],['모듈TB연결','A31:G36']];
for(const sheet of wb.worksheets.items){
 if(/^(13_|14_|15_)/.test(sheet.name)){
  views.push([sheet.name,'A1:F4']);
  if(['13_검토후보','13_규칙검토범위','13_전표계정조합','14_규칙적용','14_전표메타대사','15_계좌잔액대사','15_현금배부표','15_은행장부잔여'].includes(sheet.name))views.push([sheet.name,'G1:O4']);
 }
}
for(const [pid,last]of [['G01',42],['I01',31],['H01',40]])for(const range of ['A1:B19','A20:B25',`A26:B${last}`])views.push(['조서_'+pid,range]);
for(const [sheetName,range]of views){
 const blob=await wb.render({sheetName,range,scale:1,format:'png'}),preview=`${String(records.length+1).padStart(3,'0')}_${sheetName}_${range.replace(':','-')}.png`;
 await fs.writeFile(path.join(dir,preview),new Uint8Array(await blob.arrayBuffer()));records.push({sheet:sheetName,range,preview});
}
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:2000});
await fs.writeFile(path.join(root,'검증/출력조서_렌더검증.json'),JSON.stringify({file:path.relative(root,file),readOnly:true,records,errors:errors.ndjson},null,2));
console.log(JSON.stringify({previews:records.length,errors:errors.ndjson}));
