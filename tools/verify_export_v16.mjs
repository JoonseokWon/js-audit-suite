// Read-only previews of the application's own saved workpapers.
import fs from 'node:fs/promises';import path from 'node:path';
import {SpreadsheetFile,FileBlob} from '@oai/artifact-tool';
const root=path.resolve(import.meta.dirname,'..'),dir=path.join(root,'검증/v16_조서미리보기');await fs.mkdir(dir,{recursive:true});
const records=[],errors=[];
for(const code of ['JS','JS_ELEC','JS_AUTO','JS_SEMI','JS_BIO']){
 const file=path.join(root,`검증/소스UI_3/${code}_미검토초안.xlsx`),wb=await SpreadsheetFile.importXlsx(await FileBlob.load(file));
 const views=[['조서표지','A1:B13'],['모듈TB연결','A1:G8'],['조서_A10','A1:B12'],['조서_A10','A13:B25']];
 for(const [sheetName,range]of views){
  const blob=await wb.render({sheetName,range,scale:1,format:'png'}),preview=`${code}_${sheetName}_${range.replace(':','-')}.png`;
  await fs.writeFile(path.join(dir,preview),new Uint8Array(await blob.arrayBuffer()));records.push({company:code,sheet:sheetName,range,preview});
 }
 const result=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:1000});
 errors.push({company:code,result:result.ndjson});
}
await fs.writeFile(path.join(root,'검증/출력조서_렌더검증.json'),JSON.stringify({readOnly:true,records,errors},null,2));console.log(JSON.stringify({previews:records.length,errors}));
