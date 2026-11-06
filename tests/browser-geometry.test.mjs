import test from 'node:test';
import assert from 'node:assert/strict';
import { letterbox, decode } from '../public/inference/geometry.mjs';
test('wide frame reverses letterbox padding without shifting boxes', () => {
  const box = letterbox(1280,720);
  const [d] = decode(new Float32Array([64,176,320,356,0.9,0]),[1,1,6],1280,720,box);
  assert.equal(d.x,10); assert.equal(d.y,10); assert.equal(d.width,40); assert.equal(d.height,50);
});
test('portrait frame clips padding and filters low confidence', () => {
  const box=letterbox(480,640);
  const result=decode(new Float32Array([0,0,640,640,0.9,0,80,0,560,640,0.1,0]),[1,2,6],480,640,box);
  assert.equal(result.length,1); assert.equal(result[0].width,100); assert.equal(result[0].x,0);
});
test('invalid model contract and NaN fail rather than report zero people', () => {
  assert.throws(()=>decode(new Float32Array(6),[1,6,1],640,640,letterbox(640,640)));
  assert.throws(()=>decode(new Float32Array([0,0,1,1,NaN,0]),[1,1,6],640,640,letterbox(640,640)));
});
