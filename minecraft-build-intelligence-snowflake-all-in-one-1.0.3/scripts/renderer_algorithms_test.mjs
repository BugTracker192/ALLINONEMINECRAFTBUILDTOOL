#!/usr/bin/env node
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const root = process.argv[2];
const load = async (name) => import(pathToFileURL(path.join(root, `${name}.js`)).href);
const { fitCamera } = await load('cameraPresets');
const { fluidSurface } = await load('fluid');
const { aabbIntersectsFrustum, prioritizeVisibleChunks } = await load('frustum');
const { greedyMesh } = await load('greedyMesher');
const { specialRendererFor } = await load('specialRenderers');
const { multiplySrgb, stateTintIndex } = await load('tint');

const fit = fitCamera({min: [0,0,0], max: [9,19,29]}, 'isometric_se', 16/9, 1.1);
assert.equal(fit.target[0], 5);
assert.equal(fit.target[1], 10);
assert.equal(fit.target[2], 15);
assert.ok(fit.far > fit.near && fit.orthographicHalfWidth > fit.orthographicHalfHeight);

const water = {kind: 'water', level: 0, falling: false};
const surface = fluidSurface(water, [null,null,null,null,null,null,null,null]);
assert.deepEqual(surface, {nw:1, ne:1, se:1, sw:1, sideMask:15});
assert.throws(() => fluidSurface(water, []));

const planes = [{normal:[1,0,0],constant:0},{normal:[-1,0,0],constant:10}];
assert.equal(aabbIntersectsFrustum({min:[1,0,0],max:[2,1,1]}, planes), true);
assert.equal(aabbIntersectsFrustum({min:[-3,0,0],max:[-1,1,1]}, planes), false);
const ordered = prioritizeVisibleChunks([
  {key:'far', bounds:{min:[8,0,0],max:[9,1,1]}, center:[8.5,0.5,0.5]},
  {key:'near', bounds:{min:[1,0,0],max:[2,1,1]}, center:[1.5,0.5,0.5]},
], planes, [0,0,0]);
assert.deepEqual(ordered.map(x => x.key), ['near','far']);

const field = {size:[2,1,1], get(x,y,z){return x>=0&&x<2&&y===0&&z===0?1:0;}};
const quads = greedyMesh(field);
assert.equal(quads.length, 6, 'two adjacent equal cubes should greedy-merge into six outer quads');
assert.ok(quads.some(q => q.size[0] === 2 || q.size[1] === 2));

assert.equal(specialRendererFor('minecraft:oak_sign[rotation=0]')?.tier, 'static_approximation');
assert.equal(specialRendererFor('minecraft:stone'), null);
assert.equal(stateTintIndex('minecraft:redstone_wire[power=15]', 0), 0xff4000);
assert.equal(multiplySrgb(0xffffff, 0x123456), 0x123456);
console.log(JSON.stringify({passed:true, assertions:18}));
