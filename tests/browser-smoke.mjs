import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import assert from 'node:assert/strict';
const root=resolve('dist');
const types={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.wasm':'application/wasm','.json':'application/json','.css':'text/css'};
const server=createServer(async (req,res)=>{
  try {
    const path=resolve(root,'.'+new URL(req.url,'http://localhost').pathname.replace(/\/$/,'/index.html'));
    if(!path.startsWith(root+'/'))throw Error('Invalid path');
    const data=await readFile(path);res.writeHead(200,{'Content-Type':types[extname(path)]||'application/octet-stream'});res.end(data);
  }catch {res.writeHead(404,{'Content-Type':'application/json'});res.end('{"detail":"Not found"}');}
});
await new Promise(resolve=>server.listen(4173,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:4173/');
  await page.getByRole('button',{name:'Open sample dashboard'}).click();
  await page.getByText('SAMPLE-001 / Bus DEMO',{exact:true}).waitFor();
  const result=await page.evaluate(async()=>{
    const worker=new Worker('/inference/worker.mjs',{type:'module'});
    function call(message,transfer=[]) { return new Promise((resolve,reject)=>{ const timer=setTimeout(()=>reject(Error('Worker timeout')),180000);worker.onmessage=({data})=>{clearTimeout(timer);data.error?reject(Error(data.error)):resolve(data.result)};worker.onerror=e=>reject(Error(e.message));worker.postMessage(message,transfer);}); }
    try {
      const info=await call({id:1,type:'init'});
      const canvas=new OffscreenCanvas(640,480),ctx=canvas.getContext('2d');
      ctx.fillStyle='#999';ctx.fillRect(0,0,640,480);ctx.fillStyle='#333';ctx.fillRect(80,80,100,200);
      const bitmap=canvas.transferToImageBitmap(),start=performance.now();
      const prediction=await call({id:2,type:'predict',bitmap,capturedAt:Date.now()/1000},[bitmap]);
      return {info,prediction,elapsedMs:performance.now()-start};
    } finally {worker.terminate();}
  });
  assert.equal(result.prediction.model_loaded,true);
  assert.equal(result.prediction.frame_status,'valid');
  assert.ok(Array.isArray(result.prediction.detections));
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({provider:result.info.provider,elapsedMs:result.elapsedMs,status:result.prediction.frame_status}));
  await page.setViewportSize({width:800,height:900});
  await page.getByRole('heading',{name:'Open SafeSense on a computer'}).waitFor();
  console.log('Desktop sample, real ONNX browser inference, and small-screen guard passed.');
} finally {await browser.close();server.close();}
