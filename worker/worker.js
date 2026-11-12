(function(nacl) {
'use strict';

// Ported in 2014 by Dmitry Chestnykh and Devi Mandiri.
// Public domain.
//
// Implementation derived from TweetNaCl version 20140427.
// See for details: http://tweetnacl.cr.yp.to/

var u64 = function(h, l) { this.hi = h|0 >>> 0; this.lo = l|0 >>> 0; };
var gf = function(init) {
  var i, r = new Float64Array(16);
  if (init) for (i = 0; i < init.length; i++) r[i] = init[i];
  return r;
};

//  Pluggable, initialized in high-level API below.
var randombytes = function(/* x, n */) { throw new Error('no PRNG'); };

var _0 = new Uint8Array(16);
var _9 = new Uint8Array(32); _9[0] = 9;

var gf0 = gf(),
    gf1 = gf([1]),
    _121665 = gf([0xdb41, 1]),
    D = gf([0x78a3, 0x1359, 0x4dca, 0x75eb, 0xd8ab, 0x4141, 0x0a4d, 0x0070, 0xe898, 0x7779, 0x4079, 0x8cc7, 0xfe73, 0x2b6f, 0x6cee, 0x5203]),
    D2 = gf([0xf159, 0x26b2, 0x9b94, 0xebd6, 0xb156, 0x8283, 0x149a, 0x00e0, 0xd130, 0xeef3, 0x80f2, 0x198e, 0xfce7, 0x56df, 0xd9dc, 0x2406]),
    X = gf([0xd51a, 0x8f25, 0x2d60, 0xc956, 0xa7b2, 0x9525, 0xc760, 0x692c, 0xdc5c, 0xfdd6, 0xe231, 0xc0a4, 0x53fe, 0xcd6e, 0x36d3, 0x2169]),
    Y = gf([0x6658, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666]),
    I = gf([0xa0b0, 0x4a0e, 0x1b27, 0xc4ee, 0xe478, 0xad2f, 0x1806, 0x2f43, 0xd7a7, 0x3dfb, 0x0099, 0x2b4d, 0xdf0b, 0x4fc1, 0x2480, 0x2b83]);

function L32(x, c) { return (x << c) | (x >>> (32 - c)); }

function ld32(x, i) {
  var u = x[i+3] & 0xff;
  u = (u<<8)|(x[i+2] & 0xff);
  u = (u<<8)|(x[i+1] & 0xff);
  return (u<<8)|(x[i+0] & 0xff);
}

function dl64(x, i) {
  var h = (x[i] << 24) | (x[i+1] << 16) | (x[i+2] << 8) | x[i+3];
  var l = (x[i+4] << 24) | (x[i+5] << 16) | (x[i+6] << 8) | x[i+7];
  return new u64(h, l);
}

function st32(x, j, u) {
  var i;
  for (i = 0; i < 4; i++) { x[j+i] = u & 255; u >>>= 8; }
}

function ts64(x, i, u) {
  x[i]   = (u.hi >> 24) & 0xff;
  x[i+1] = (u.hi >> 16) & 0xff;
  x[i+2] = (u.hi >>  8) & 0xff;
  x[i+3] = u.hi & 0xff;
  x[i+4] = (u.lo >> 24)  & 0xff;
  x[i+5] = (u.lo >> 16)  & 0xff;
  x[i+6] = (u.lo >>  8)  & 0xff;
  x[i+7] = u.lo & 0xff;
}

function vn(x, xi, y, yi, n) {
  var i,d = 0;
  for (i = 0; i < n; i++) d |= x[xi+i]^y[yi+i];
  return (1 & ((d - 1) >>> 8)) - 1;
}

function crypto_verify_16(x, xi, y, yi) {
  return vn(x,xi,y,yi,16);
}

function crypto_verify_32(x, xi, y, yi) {
  return vn(x,xi,y,yi,32);
}

function core(out,inp,k,c,h) {
  var w = new Uint32Array(16), x = new Uint32Array(16),
      y = new Uint32Array(16), t = new Uint32Array(4);
  var i, j, m;

  for (i = 0; i < 4; i++) {
    x[5*i] = ld32(c, 4*i);
    x[1+i] = ld32(k, 4*i);
    x[6+i] = ld32(inp, 4*i);
    x[11+i] = ld32(k, 16+4*i);
  }

  for (i = 0; i < 16; i++) y[i] = x[i];

  for (i = 0; i < 20; i++) {
    for (j = 0; j < 4; j++) {
      for (m = 0; m < 4; m++) t[m] = x[(5*j+4*m)%16];
      t[1] ^= L32((t[0]+t[3])|0, 7);
      t[2] ^= L32((t[1]+t[0])|0, 9);
      t[3] ^= L32((t[2]+t[1])|0,13);
      t[0] ^= L32((t[3]+t[2])|0,18);
      for (m = 0; m < 4; m++) w[4*j+(j+m)%4] = t[m];
    }
    for (m = 0; m < 16; m++) x[m] = w[m];
  }

  if (h) {
    for (i = 0; i < 16; i++) x[i] = (x[i] + y[i]) | 0;
    for (i = 0; i < 4; i++) {
      x[5*i] = (x[5*i] - ld32(c, 4*i)) | 0;
      x[6+i] = (x[6+i] - ld32(inp, 4*i)) | 0;
    }
    for (i = 0; i < 4; i++) {
      st32(out,4*i,x[5*i]);
      st32(out,16+4*i,x[6+i]);
    }
  } else {
    for (i = 0; i < 16; i++) st32(out, 4 * i, (x[i] + y[i]) | 0);
  }
}

function crypto_core_salsa20(out,inp,k,c) {
  core(out,inp,k,c,false);
  return 0;
}

function crypto_core_hsalsa20(out,inp,k,c) {
  core(out,inp,k,c,true);
  return 0;
}

var sigma = new Uint8Array([101, 120, 112, 97, 110, 100, 32, 51, 50, 45, 98, 121, 116, 101, 32, 107]);
            // "expand 32-byte k"

function crypto_stream_salsa20_xor(c,cpos,m,mpos,b,n,k) {
  var z = new Uint8Array(16), x = new Uint8Array(64);
  var u, i;
  if (!b) return 0;
  for (i = 0; i < 16; i++) z[i] = 0;
  for (i = 0; i < 8; i++) z[i] = n[i];
  while (b >= 64) {
    crypto_core_salsa20(x,z,k,sigma);
    for (i = 0; i < 64; i++) c[cpos+i] = (m?m[mpos+i]:0) ^ x[i];
    u = 1;
    for (i = 8; i < 16; i++) {
      u = u + (z[i] & 0xff) | 0;
      z[i] = u & 0xff;
      u >>>= 8;
    }
    b -= 64;
    cpos += 64;
    if (m) mpos += 64;
  }
  if (b > 0) {
    crypto_core_salsa20(x,z,k,sigma);
    for (i = 0; i < b; i++) c[cpos+i] = (m?m[mpos+i]:0) ^ x[i];
  }
  return 0;
}

function crypto_stream_salsa20(c,cpos,d,n,k) {
  return crypto_stream_salsa20_xor(c,cpos,null,0,d,n,k);
}

function crypto_stream(c,cpos,d,n,k) {
  var s = new Uint8Array(32);
  crypto_core_hsalsa20(s,n,k,sigma);
  return crypto_stream_salsa20(c,cpos,d,n.subarray(16),s);
}

function crypto_stream_xor(c,cpos,m,mpos,d,n,k) {
  var s = new Uint8Array(32);
  crypto_core_hsalsa20(s,n,k,sigma);
  return crypto_stream_salsa20_xor(c,cpos,m,mpos,d,n.subarray(16),s);
}

function add1305(h, c) {
  var j, u = 0;
  for (j = 0; j < 17; j++) {
    u = (u + ((h[j] + c[j]) | 0)) | 0;
    h[j] = u & 255;
    u >>>= 8;
  }
}

var minusp = new Uint32Array([
  5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 252
]);

function crypto_onetimeauth(out, outpos, m, mpos, n, k) {
  var s, i, j, u;
  var x = new Uint32Array(17), r = new Uint32Array(17),
      h = new Uint32Array(17), c = new Uint32Array(17),
      g = new Uint32Array(17);
  for (j = 0; j < 17; j++) r[j]=h[j]=0;
  for (j = 0; j < 16; j++) r[j]=k[j];
  r[3]&=15;
  r[4]&=252;
  r[7]&=15;
  r[8]&=252;
  r[11]&=15;
  r[12]&=252;
  r[15]&=15;

  while (n > 0) {
    for (j = 0; j < 17; j++) c[j] = 0;
    for (j = 0; (j < 16) && (j < n); ++j) c[j] = m[mpos+j];
    c[j] = 1;
    mpos += j; n -= j;
    add1305(h,c);
    for (i = 0; i < 17; i++) {
      x[i] = 0;
      for (j = 0; j < 17; j++) x[i] = (x[i] + (h[j] * ((j <= i) ? r[i - j] : ((320 * r[i + 17 - j])|0))) | 0) | 0;
    }
    for (i = 0; i < 17; i++) h[i] = x[i];
    u = 0;
    for (j = 0; j < 16; j++) {
      u = (u + h[j]) | 0;
      h[j] = u & 255;
      u >>>= 8;
    }
    u = (u + h[16]) | 0; h[16] = u & 3;
    u = (5 * (u >>> 2)) | 0;
    for (j = 0; j < 16; j++) {
      u = (u + h[j]) | 0;
      h[j] = u & 255;
      u >>>= 8;
    }
    u = (u + h[16]) | 0; h[16] = u;
  }

  for (j = 0; j < 17; j++) g[j] = h[j];
  add1305(h,minusp);
  s = (-(h[16] >>> 7) | 0);
  for (j = 0; j < 17; j++) h[j] ^= s & (g[j] ^ h[j]);

  for (j = 0; j < 16; j++) c[j] = k[j + 16];
  c[16] = 0;
  add1305(h,c);
  for (j = 0; j < 16; j++) out[outpos+j] = h[j];
  return 0;
}

function crypto_onetimeauth_verify(h, hpos, m, mpos, n, k) {
  var x = new Uint8Array(16);
  crypto_onetimeauth(x,0,m,mpos,n,k);
  return crypto_verify_16(h,hpos,x,0);
}

function crypto_secretbox(c,m,d,n,k) {
  var i;
  if (d < 32) return -1;
  crypto_stream_xor(c,0,m,0,d,n,k);
  crypto_onetimeauth(c, 16, c, 32, d - 32, c);
  for (i = 0; i < 16; i++) c[i] = 0;
  return 0;
}

function crypto_secretbox_open(m,c,d,n,k) {
  var i;
  var x = new Uint8Array(32);
  if (d < 32) return -1;
  crypto_stream(x,0,32,n,k);
  if (crypto_onetimeauth_verify(c, 16,c, 32,d - 32,x) !== 0) return -1;
  crypto_stream_xor(m,0,c,0,d,n,k);
  for (i = 0; i < 32; i++) m[i] = 0;
  return 0;
}

function set25519(r, a) {
  var i;
  for (i = 0; i < 16; i++) r[i] = a[i]|0;
}

function car25519(o) {
  var c;
  var i;
  for (i = 0; i < 16; i++) {
      o[i] += 65536;
      c = Math.floor(o[i] / 65536);
      o[(i+1)*(i<15?1:0)] += c - 1 + 37 * (c-1) * (i===15?1:0);
      o[i] -= (c * 65536);
  }
}

function sel25519(p, q, b) {
  var t, c = ~(b-1);
  for (var i = 0; i < 16; i++) {
    t = c & (p[i] ^ q[i]);
    p[i] ^= t;
    q[i] ^= t;
  }
}

function pack25519(o, n) {
  var i, j, b;
  var m = gf(), t = gf();
  for (i = 0; i < 16; i++) t[i] = n[i];
  car25519(t);
  car25519(t);
  car25519(t);
  for (j = 0; j < 2; j++) {
    m[0] = t[0] - 0xffed;
    for (i = 1; i < 15; i++) {
      m[i] = t[i] - 0xffff - ((m[i-1]>>16) & 1);
      m[i-1] &= 0xffff;
    }
    m[15] = t[15] - 0x7fff - ((m[14]>>16) & 1);
    b = (m[15]>>16) & 1;
    m[14] &= 0xffff;
    sel25519(t, m, 1-b);
  }
  for (i = 0; i < 16; i++) {
    o[2*i] = t[i] & 0xff;
    o[2*i+1] = t[i]>>8;
  }
}

function neq25519(a, b) {
  var c = new Uint8Array(32), d = new Uint8Array(32);
  pack25519(c, a);
  pack25519(d, b);
  return crypto_verify_32(c, 0, d, 0);
}

function par25519(a) {
  var d = new Uint8Array(32);
  pack25519(d, a);
  return d[0] & 1;
}

function unpack25519(o, n) {
  var i;
  for (i = 0; i < 16; i++) o[i] = n[2*i] + (n[2*i+1] << 8);
  o[15] &= 0x7fff;
}

function A(o, a, b) {
  var i;
  for (i = 0; i < 16; i++) o[i] = (a[i] + b[i])|0;
}

function Z(o, a, b) {
  var i;
  for (i = 0; i < 16; i++) o[i] = (a[i] - b[i])|0;
}

function M(o, a, b) {
  var i, j, t = new Float64Array(31);
  for (i = 0; i < 31; i++) t[i] = 0;
  for (i = 0; i < 16; i++) {
    for (j = 0; j < 16; j++) {
      t[i+j] += a[i] * b[j];
    }
  }
  for (i = 0; i < 15; i++) {
    t[i] += 38 * t[i+16];
  }
  for (i = 0; i < 16; i++) o[i] = t[i];
  car25519(o);
  car25519(o);
}

function S(o, a) {
  M(o, a, a);
}

function inv25519(o, i) {
  var c = gf();
  var a;
  for (a = 0; a < 16; a++) c[a] = i[a];
  for (a = 253; a >= 0; a--) {
    S(c, c);
    if(a !== 2 && a !== 4) M(c, c, i);
  }
  for (a = 0; a < 16; a++) o[a] = c[a];
}

function pow2523(o, i) {
  var c = gf();
  var a;
  for (a = 0; a < 16; a++) c[a] = i[a];
  for (a = 250; a >= 0; a--) {
      S(c, c);
      if(a !== 1) M(c, c, i);
  }
  for (a = 0; a < 16; a++) o[a] = c[a];
}

function crypto_scalarmult(q, n, p) {
  var z = new Uint8Array(32);
  var x = new Float64Array(80), r, i;
  var a = gf(), b = gf(), c = gf(),
      d = gf(), e = gf(), f = gf();
  for (i = 0; i < 31; i++) z[i] = n[i];
  z[31]=(n[31]&127)|64;
  z[0]&=248;
  unpack25519(x,p);
  for (i = 0; i < 16; i++) {
    b[i]=x[i];
    d[i]=a[i]=c[i]=0;
  }
  a[0]=d[0]=1;
  for (i=254; i>=0; --i) {
    r=(z[i>>>3]>>>(i&7))&1;
    sel25519(a,b,r);
    sel25519(c,d,r);
    A(e,a,c);
    Z(a,a,c);
    A(c,b,d);
    Z(b,b,d);
    S(d,e);
    S(f,a);
    M(a,c,a);
    M(c,b,e);
    A(e,a,c);
    Z(a,a,c);
    S(b,a);
    Z(c,d,f);
    M(a,c,_121665);
    A(a,a,d);
    M(c,c,a);
    M(a,d,f);
    M(d,b,x);
    S(b,e);
    sel25519(a,b,r);
    sel25519(c,d,r);
  }
  for (i = 0; i < 16; i++) {
    x[i+16]=a[i];
    x[i+32]=c[i];
    x[i+48]=b[i];
    x[i+64]=d[i];
  }
  var x32 = x.subarray(32);
  var x16 = x.subarray(16);
  inv25519(x32,x32);
  M(x16,x16,x32);
  pack25519(q,x16);
  return 0;
}

function crypto_scalarmult_base(q, n) {
  return crypto_scalarmult(q, n, _9);
}

function crypto_box_keypair(y, x) {
  randombytes(x, 32);
  return crypto_scalarmult_base(y, x);
}

function crypto_box_beforenm(k, y, x) {
  var s = new Uint8Array(32);
  crypto_scalarmult(s, x, y);
  return crypto_core_hsalsa20(k, _0, s, sigma);
}

var crypto_box_afternm = crypto_secretbox;
var crypto_box_open_afternm = crypto_secretbox_open;

function crypto_box(c, m, d, n, y, x) {
  var k = new Uint8Array(32);
  crypto_box_beforenm(k, y, x);
  return crypto_box_afternm(c, m, d, n, k);
}

function crypto_box_open(m, c, d, n, y, x) {
  var k = new Uint8Array(32);
  crypto_box_beforenm(k, y, x);
  return crypto_box_open_afternm(m, c, d, n, k);
}

function add64() {
  var a = 0, b = 0, c = 0, d = 0, m16 = 65535, l, h, i;
  for (i = 0; i < arguments.length; i++) {
    l = arguments[i].lo;
    h = arguments[i].hi;
    a += (l & m16); b += (l >>> 16);
    c += (h & m16); d += (h >>> 16);
  }

  b += (a >>> 16);
  c += (b >>> 16);
  d += (c >>> 16);

  return new u64((c & m16) | (d << 16), (a & m16) | (b << 16));
}

function shr64(x, c) {
  return new u64((x.hi >>> c), (x.lo >>> c) | (x.hi << (32 - c)));
}

function xor64() {
  var l = 0, h = 0, i;
  for (i = 0; i < arguments.length; i++) {
    l ^= arguments[i].lo;
    h ^= arguments[i].hi;
  }
  return new u64(h, l);
}

function R(x, c) {
  var h, l, c1 = 32 - c;
  if (c < 32) {
    h = (x.hi >>> c) | (x.lo << c1);
    l = (x.lo >>> c) | (x.hi << c1);
  } else if (c < 64) {
    h = (x.lo >>> c) | (x.hi << c1);
    l = (x.hi >>> c) | (x.lo << c1);
  }
  return new u64(h, l);
}

function Ch(x, y, z) {
  var h = (x.hi & y.hi) ^ (~x.hi & z.hi),
      l = (x.lo & y.lo) ^ (~x.lo & z.lo);
  return new u64(h, l);
}

function Maj(x, y, z) {
  var h = (x.hi & y.hi) ^ (x.hi & z.hi) ^ (y.hi & z.hi),
      l = (x.lo & y.lo) ^ (x.lo & z.lo) ^ (y.lo & z.lo);
  return new u64(h, l);
}

function Sigma0(x) { return xor64(R(x,28), R(x,34), R(x,39)); }
function Sigma1(x) { return xor64(R(x,14), R(x,18), R(x,41)); }
function sigma0(x) { return xor64(R(x, 1), R(x, 8), shr64(x,7)); }
function sigma1(x) { return xor64(R(x,19), R(x,61), shr64(x,6)); }

var K = [
  new u64(0x428a2f98, 0xd728ae22), new u64(0x71374491, 0x23ef65cd),
  new u64(0xb5c0fbcf, 0xec4d3b2f), new u64(0xe9b5dba5, 0x8189dbbc),
  new u64(0x3956c25b, 0xf348b538), new u64(0x59f111f1, 0xb605d019),
  new u64(0x923f82a4, 0xaf194f9b), new u64(0xab1c5ed5, 0xda6d8118),
  new u64(0xd807aa98, 0xa3030242), new u64(0x12835b01, 0x45706fbe),
  new u64(0x243185be, 0x4ee4b28c), new u64(0x550c7dc3, 0xd5ffb4e2),
  new u64(0x72be5d74, 0xf27b896f), new u64(0x80deb1fe, 0x3b1696b1),
  new u64(0x9bdc06a7, 0x25c71235), new u64(0xc19bf174, 0xcf692694),
  new u64(0xe49b69c1, 0x9ef14ad2), new u64(0xefbe4786, 0x384f25e3),
  new u64(0x0fc19dc6, 0x8b8cd5b5), new u64(0x240ca1cc, 0x77ac9c65),
  new u64(0x2de92c6f, 0x592b0275), new u64(0x4a7484aa, 0x6ea6e483),
  new u64(0x5cb0a9dc, 0xbd41fbd4), new u64(0x76f988da, 0x831153b5),
  new u64(0x983e5152, 0xee66dfab), new u64(0xa831c66d, 0x2db43210),
  new u64(0xb00327c8, 0x98fb213f), new u64(0xbf597fc7, 0xbeef0ee4),
  new u64(0xc6e00bf3, 0x3da88fc2), new u64(0xd5a79147, 0x930aa725),
  new u64(0x06ca6351, 0xe003826f), new u64(0x14292967, 0x0a0e6e70),
  new u64(0x27b70a85, 0x46d22ffc), new u64(0x2e1b2138, 0x5c26c926),
  new u64(0x4d2c6dfc, 0x5ac42aed), new u64(0x53380d13, 0x9d95b3df),
  new u64(0x650a7354, 0x8baf63de), new u64(0x766a0abb, 0x3c77b2a8),
  new u64(0x81c2c92e, 0x47edaee6), new u64(0x92722c85, 0x1482353b),
  new u64(0xa2bfe8a1, 0x4cf10364), new u64(0xa81a664b, 0xbc423001),
  new u64(0xc24b8b70, 0xd0f89791), new u64(0xc76c51a3, 0x0654be30),
  new u64(0xd192e819, 0xd6ef5218), new u64(0xd6990624, 0x5565a910),
  new u64(0xf40e3585, 0x5771202a), new u64(0x106aa070, 0x32bbd1b8),
  new u64(0x19a4c116, 0xb8d2d0c8), new u64(0x1e376c08, 0x5141ab53),
  new u64(0x2748774c, 0xdf8eeb99), new u64(0x34b0bcb5, 0xe19b48a8),
  new u64(0x391c0cb3, 0xc5c95a63), new u64(0x4ed8aa4a, 0xe3418acb),
  new u64(0x5b9cca4f, 0x7763e373), new u64(0x682e6ff3, 0xd6b2b8a3),
  new u64(0x748f82ee, 0x5defb2fc), new u64(0x78a5636f, 0x43172f60),
  new u64(0x84c87814, 0xa1f0ab72), new u64(0x8cc70208, 0x1a6439ec),
  new u64(0x90befffa, 0x23631e28), new u64(0xa4506ceb, 0xde82bde9),
  new u64(0xbef9a3f7, 0xb2c67915), new u64(0xc67178f2, 0xe372532b),
  new u64(0xca273ece, 0xea26619c), new u64(0xd186b8c7, 0x21c0c207),
  new u64(0xeada7dd6, 0xcde0eb1e), new u64(0xf57d4f7f, 0xee6ed178),
  new u64(0x06f067aa, 0x72176fba), new u64(0x0a637dc5, 0xa2c898a6),
  new u64(0x113f9804, 0xbef90dae), new u64(0x1b710b35, 0x131c471b),
  new u64(0x28db77f5, 0x23047d84), new u64(0x32caab7b, 0x40c72493),
  new u64(0x3c9ebe0a, 0x15c9bebc), new u64(0x431d67c4, 0x9c100d4c),
  new u64(0x4cc5d4be, 0xcb3e42b6), new u64(0x597f299c, 0xfc657e2a),
  new u64(0x5fcb6fab, 0x3ad6faec), new u64(0x6c44198c, 0x4a475817)
];

function crypto_hashblocks(x, m, n) {
  var z = [], b = [], a = [], w = [], t, i, j;

  for (i = 0; i < 8; i++) z[i] = a[i] = dl64(x, 8*i);

  var pos = 0;
  while (n >= 128) {
    for (i = 0; i < 16; i++) w[i] = dl64(m, 8*i+pos);
    for (i = 0; i < 80; i++) {
      for (j = 0; j < 8; j++) b[j] = a[j];
      t = add64(a[7], Sigma1(a[4]), Ch(a[4], a[5], a[6]), K[i], w[i%16]);
      b[7] = add64(t, Sigma0(a[0]), Maj(a[0], a[1], a[2]));
      b[3] = add64(b[3], t);
      for (j = 0; j < 8; j++) a[(j+1)%8] = b[j];
      if (i%16 === 15) {
        for (j = 0; j < 16; j++) {
          w[j] = add64(w[j], w[(j+9)%16], sigma0(w[(j+1)%16]), sigma1(w[(j+14)%16]));
        }
      }
    }

    for (i = 0; i < 8; i++) {
      a[i] = add64(a[i], z[i]);
      z[i] = a[i];
    }

    pos += 128;
    n -= 128;
  }

  for (i = 0; i < 8; i++) ts64(x, 8*i, z[i]);
  return n;
}

var iv = new Uint8Array([
  0x6a,0x09,0xe6,0x67,0xf3,0xbc,0xc9,0x08,
  0xbb,0x67,0xae,0x85,0x84,0xca,0xa7,0x3b,
  0x3c,0x6e,0xf3,0x72,0xfe,0x94,0xf8,0x2b,
  0xa5,0x4f,0xf5,0x3a,0x5f,0x1d,0x36,0xf1,
  0x51,0x0e,0x52,0x7f,0xad,0xe6,0x82,0xd1,
  0x9b,0x05,0x68,0x8c,0x2b,0x3e,0x6c,0x1f,
  0x1f,0x83,0xd9,0xab,0xfb,0x41,0xbd,0x6b,
  0x5b,0xe0,0xcd,0x19,0x13,0x7e,0x21,0x79
]);

function crypto_hash(out, m, n) {
  var h = new Uint8Array(64), x = new Uint8Array(256);
  var i, b = n;

  for (i = 0; i < 64; i++) h[i] = iv[i];

  crypto_hashblocks(h, m, n);
  n %= 128;

  for (i = 0; i < 256; i++) x[i] = 0;
  for (i = 0; i < n; i++) x[i] = m[b-n+i];
  x[n] = 128;

  n = 256-128*(n<112?1:0);
  x[n-9] = 0;
  ts64(x, n-8, new u64((b / 0x20000000) | 0, b << 3));
  crypto_hashblocks(h, x, n);

  for (i = 0; i < 64; i++) out[i] = h[i];

  return 0;
}

function add(p, q) {
  var a = gf(), b = gf(), c = gf(),
      d = gf(), e = gf(), f = gf(),
      g = gf(), h = gf(), t = gf();

  Z(a, p[1], p[0]);
  Z(t, q[1], q[0]);
  M(a, a, t);
  A(b, p[0], p[1]);
  A(t, q[0], q[1]);
  M(b, b, t);
  M(c, p[3], q[3]);
  M(c, c, D2);
  M(d, p[2], q[2]);
  A(d, d, d);
  Z(e, b, a);
  Z(f, d, c);
  A(g, d, c);
  A(h, b, a);

  M(p[0], e, f);
  M(p[1], h, g);
  M(p[2], g, f);
  M(p[3], e, h);
}

function cswap(p, q, b) {
  var i;
  for (i = 0; i < 4; i++) {
    sel25519(p[i], q[i], b);
  }
}

function pack(r, p) {
  var tx = gf(), ty = gf(), zi = gf();
  inv25519(zi, p[2]);
  M(tx, p[0], zi);
  M(ty, p[1], zi);
  pack25519(r, ty);
  r[31] ^= par25519(tx) << 7;
}

function scalarmult(p, q, s) {
  var b, i;
  set25519(p[0], gf0);
  set25519(p[1], gf1);
  set25519(p[2], gf1);
  set25519(p[3], gf0);
  for (i = 255; i >= 0; --i) {
    b = (s[(i/8)|0] >> (i&7)) & 1;
    cswap(p, q, b);
    add(q, p);
    add(p, p);
    cswap(p, q, b);
  }
}

function scalarbase(p, s) {
  var q = [gf(), gf(), gf(), gf()];
  set25519(q[0], X);
  set25519(q[1], Y);
  set25519(q[2], gf1);
  M(q[3], X, Y);
  scalarmult(p, q, s);
}

function crypto_sign_keypair(pk, sk, seeded) {
  var d = new Uint8Array(64);
  var p = [gf(), gf(), gf(), gf()];
  var i;

  if (!seeded) randombytes(sk, 32);
  crypto_hash(d, sk, 32);
  d[0] &= 248;
  d[31] &= 127;
  d[31] |= 64;

  scalarbase(p, d);
  pack(pk, p);

  for (i = 0; i < 32; i++) sk[i+32] = pk[i];
  return 0;
}

var L = new Float64Array([0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10]);

function modL(r, x) {
  var carry, i, j, k;
  for (i = 63; i >= 32; --i) {
    carry = 0;
    for (j = i - 32, k = i - 12; j < k; ++j) {
      x[j] += carry - 16 * x[i] * L[j - (i - 32)];
      carry = Math.floor((x[j] + 128) / 256);
      x[j] -= carry * 256;
    }
    x[j] += carry;
    x[i] = 0;
  }
  carry = 0;
  for (j = 0; j < 32; j++) {
    x[j] += carry - (x[31] >> 4) * L[j];
    carry = x[j] >> 8;
    x[j] &= 255;
  }
  for (j = 0; j < 32; j++) x[j] -= carry * L[j];
  for (i = 0; i < 32; i++) {
    x[i+1] += x[i] >> 8;
    r[i] = x[i] & 255;
  }
}

function reduce(r) {
  var x = new Float64Array(64), i;
  for (i = 0; i < 64; i++) x[i] = r[i];
  for (i = 0; i < 64; i++) r[i] = 0;
  modL(r, x);
}

// Note: difference from C - smlen returned, not passed as argument.
function crypto_sign(sm, m, n, sk) {
  var d = new Uint8Array(64), h = new Uint8Array(64), r = new Uint8Array(64);
  var i, j, x = new Float64Array(64);
  var p = [gf(), gf(), gf(), gf()];

  crypto_hash(d, sk, 32);
  d[0] &= 248;
  d[31] &= 127;
  d[31] |= 64;

  var smlen = n + 64;
  for (i = 0; i < n; i++) sm[64 + i] = m[i];
  for (i = 0; i < 32; i++) sm[32 + i] = d[32 + i];

  crypto_hash(r, sm.subarray(32), n+32);
  reduce(r);
  scalarbase(p, r);
  pack(sm, p);

  for (i = 32; i < 64; i++) sm[i] = sk[i];
  crypto_hash(h, sm, n + 64);
  reduce(h);

  for (i = 0; i < 64; i++) x[i] = 0;
  for (i = 0; i < 32; i++) x[i] = r[i];
  for (i = 0; i < 32; i++) {
    for (j = 0; j < 32; j++) {
      x[i+j] += h[i] * d[j];
    }
  }

  modL(sm.subarray(32), x);
  return smlen;
}

function unpackneg(r, p) {
  var t = gf(), chk = gf(), num = gf(),
      den = gf(), den2 = gf(), den4 = gf(),
      den6 = gf();

  set25519(r[2], gf1);
  unpack25519(r[1], p);
  S(num, r[1]);
  M(den, num, D);
  Z(num, num, r[2]);
  A(den, r[2], den);

  S(den2, den);
  S(den4, den2);
  M(den6, den4, den2);
  M(t, den6, num);
  M(t, t, den);

  pow2523(t, t);
  M(t, t, num);
  M(t, t, den);
  M(t, t, den);
  M(r[0], t, den);

  S(chk, r[0]);
  M(chk, chk, den);
  if (neq25519(chk, num)) M(r[0], r[0], I);

  S(chk, r[0]);
  M(chk, chk, den);
  if (neq25519(chk, num)) return -1;

  if (par25519(r[0]) === (p[31]>>7)) Z(r[0], gf0, r[0]);

  M(r[3], r[0], r[1]);
  return 0;
}

function crypto_sign_open(m, sm, n, pk) {
  var i;
  var t = new Uint8Array(32), h = new Uint8Array(64);
  var p = [gf(), gf(), gf(), gf()],
      q = [gf(), gf(), gf(), gf()];

  if (n < 64) return -1;

  if (unpackneg(q, pk)) return -1;

  for (i = 0; i < n; i++) m[i] = sm[i];
  for (i = 0; i < 32; i++) m[i+32] = pk[i];
  crypto_hash(h, m, n);
  reduce(h);
  scalarmult(p, q, h);

  scalarbase(q, sm.subarray(32));
  add(p, q);
  pack(t, p);

  n -= 64;
  if (crypto_verify_32(sm, 0, t, 0)) {
    for (i = 0; i < n; i++) m[i] = 0;
    return -1;
  }

  for (i = 0; i < n; i++) m[i] = sm[i + 64];
  return n;
}

var crypto_secretbox_KEYBYTES = 32,
    crypto_secretbox_NONCEBYTES = 24,
    crypto_secretbox_ZEROBYTES = 32,
    crypto_secretbox_BOXZEROBYTES = 16,
    crypto_scalarmult_BYTES = 32,
    crypto_scalarmult_SCALARBYTES = 32,
    crypto_box_PUBLICKEYBYTES = 32,
    crypto_box_SECRETKEYBYTES = 32,
    crypto_box_BEFORENMBYTES = 32,
    crypto_box_NONCEBYTES = crypto_secretbox_NONCEBYTES,
    crypto_box_ZEROBYTES = crypto_secretbox_ZEROBYTES,
    crypto_box_BOXZEROBYTES = crypto_secretbox_BOXZEROBYTES,
    crypto_sign_BYTES = 64,
    crypto_sign_PUBLICKEYBYTES = 32,
    crypto_sign_SECRETKEYBYTES = 64,
    crypto_sign_SEEDBYTES = 32,
    crypto_hash_BYTES = 64;

nacl.lowlevel = {
  crypto_core_hsalsa20: crypto_core_hsalsa20,
  crypto_stream_xor: crypto_stream_xor,
  crypto_stream: crypto_stream,
  crypto_stream_salsa20_xor: crypto_stream_salsa20_xor,
  crypto_stream_salsa20: crypto_stream_salsa20,
  crypto_onetimeauth: crypto_onetimeauth,
  crypto_onetimeauth_verify: crypto_onetimeauth_verify,
  crypto_verify_16: crypto_verify_16,
  crypto_verify_32: crypto_verify_32,
  crypto_secretbox: crypto_secretbox,
  crypto_secretbox_open: crypto_secretbox_open,
  crypto_scalarmult: crypto_scalarmult,
  crypto_scalarmult_base: crypto_scalarmult_base,
  crypto_box_beforenm: crypto_box_beforenm,
  crypto_box_afternm: crypto_box_afternm,
  crypto_box: crypto_box,
  crypto_box_open: crypto_box_open,
  crypto_box_keypair: crypto_box_keypair,
  crypto_hash: crypto_hash,
  crypto_sign: crypto_sign,
  crypto_sign_keypair: crypto_sign_keypair,
  crypto_sign_open: crypto_sign_open,

  crypto_secretbox_KEYBYTES: crypto_secretbox_KEYBYTES,
  crypto_secretbox_NONCEBYTES: crypto_secretbox_NONCEBYTES,
  crypto_secretbox_ZEROBYTES: crypto_secretbox_ZEROBYTES,
  crypto_secretbox_BOXZEROBYTES: crypto_secretbox_BOXZEROBYTES,
  crypto_scalarmult_BYTES: crypto_scalarmult_BYTES,
  crypto_scalarmult_SCALARBYTES: crypto_scalarmult_SCALARBYTES,
  crypto_box_PUBLICKEYBYTES: crypto_box_PUBLICKEYBYTES,
  crypto_box_SECRETKEYBYTES: crypto_box_SECRETKEYBYTES,
  crypto_box_BEFORENMBYTES: crypto_box_BEFORENMBYTES,
  crypto_box_NONCEBYTES: crypto_box_NONCEBYTES,
  crypto_box_ZEROBYTES: crypto_box_ZEROBYTES,
  crypto_box_BOXZEROBYTES: crypto_box_BOXZEROBYTES,
  crypto_sign_BYTES: crypto_sign_BYTES,
  crypto_sign_PUBLICKEYBYTES: crypto_sign_PUBLICKEYBYTES,
  crypto_sign_SECRETKEYBYTES: crypto_sign_SECRETKEYBYTES,
  crypto_sign_SEEDBYTES: crypto_sign_SEEDBYTES,
  crypto_hash_BYTES: crypto_hash_BYTES,

  gf: gf,
  D: D,
  L: L,
  pack25519: pack25519,
  unpack25519: unpack25519,
  M: M,
  A: A,
  S: S,
  Z: Z,
  pow2523: pow2523,
  add: add,
  set25519: set25519,
  modL: modL,
  scalarmult: scalarmult,
  scalarbase: scalarbase,
};

/* High-level API */

function checkLengths(k, n) {
  if (k.length !== crypto_secretbox_KEYBYTES) throw new Error('bad key size');
  if (n.length !== crypto_secretbox_NONCEBYTES) throw new Error('bad nonce size');
}

function checkBoxLengths(pk, sk) {
  if (pk.length !== crypto_box_PUBLICKEYBYTES) throw new Error('bad public key size');
  if (sk.length !== crypto_box_SECRETKEYBYTES) throw new Error('bad secret key size');
}

function checkArrayTypes() {
  for (var i = 0; i < arguments.length; i++) {
    if (!(arguments[i] instanceof Uint8Array))
      throw new TypeError('unexpected type, use Uint8Array');
  }
}

function cleanup(arr) {
  for (var i = 0; i < arr.length; i++) arr[i] = 0;
}

nacl.randomBytes = function(n) {
  var b = new Uint8Array(n);
  randombytes(b, n);
  return b;
};

nacl.secretbox = function(msg, nonce, key) {
  checkArrayTypes(msg, nonce, key);
  checkLengths(key, nonce);
  var m = new Uint8Array(crypto_secretbox_ZEROBYTES + msg.length);
  var c = new Uint8Array(m.length);
  for (var i = 0; i < msg.length; i++) m[i+crypto_secretbox_ZEROBYTES] = msg[i];
  crypto_secretbox(c, m, m.length, nonce, key);
  return c.subarray(crypto_secretbox_BOXZEROBYTES);
};

nacl.secretbox.open = function(box, nonce, key) {
  checkArrayTypes(box, nonce, key);
  checkLengths(key, nonce);
  var c = new Uint8Array(crypto_secretbox_BOXZEROBYTES + box.length);
  var m = new Uint8Array(c.length);
  for (var i = 0; i < box.length; i++) c[i+crypto_secretbox_BOXZEROBYTES] = box[i];
  if (c.length < 32) return null;
  if (crypto_secretbox_open(m, c, c.length, nonce, key) !== 0) return null;
  return m.subarray(crypto_secretbox_ZEROBYTES);
};

nacl.secretbox.keyLength = crypto_secretbox_KEYBYTES;
nacl.secretbox.nonceLength = crypto_secretbox_NONCEBYTES;
nacl.secretbox.overheadLength = crypto_secretbox_BOXZEROBYTES;

nacl.scalarMult = function(n, p) {
  checkArrayTypes(n, p);
  if (n.length !== crypto_scalarmult_SCALARBYTES) throw new Error('bad n size');
  if (p.length !== crypto_scalarmult_BYTES) throw new Error('bad p size');
  var q = new Uint8Array(crypto_scalarmult_BYTES);
  crypto_scalarmult(q, n, p);
  return q;
};

nacl.scalarMult.base = function(n) {
  checkArrayTypes(n);
  if (n.length !== crypto_scalarmult_SCALARBYTES) throw new Error('bad n size');
  var q = new Uint8Array(crypto_scalarmult_BYTES);
  crypto_scalarmult_base(q, n);
  return q;
};

nacl.scalarMult.scalarLength = crypto_scalarmult_SCALARBYTES;
nacl.scalarMult.groupElementLength = crypto_scalarmult_BYTES;

nacl.box = function(msg, nonce, publicKey, secretKey) {
  var k = nacl.box.before(publicKey, secretKey);
  return nacl.secretbox(msg, nonce, k);
};

nacl.box.before = function(publicKey, secretKey) {
  checkArrayTypes(publicKey, secretKey);
  checkBoxLengths(publicKey, secretKey);
  var k = new Uint8Array(crypto_box_BEFORENMBYTES);
  crypto_box_beforenm(k, publicKey, secretKey);
  return k;
};

nacl.box.after = nacl.secretbox;

nacl.box.open = function(msg, nonce, publicKey, secretKey) {
  var k = nacl.box.before(publicKey, secretKey);
  return nacl.secretbox.open(msg, nonce, k);
};

nacl.box.open.after = nacl.secretbox.open;

nacl.box.keyPair = function() {
  var pk = new Uint8Array(crypto_box_PUBLICKEYBYTES);
  var sk = new Uint8Array(crypto_box_SECRETKEYBYTES);
  crypto_box_keypair(pk, sk);
  return {publicKey: pk, secretKey: sk};
};

nacl.box.keyPair.fromSecretKey = function(secretKey) {
  checkArrayTypes(secretKey);
  if (secretKey.length !== crypto_box_SECRETKEYBYTES)
    throw new Error('bad secret key size');
  var pk = new Uint8Array(crypto_box_PUBLICKEYBYTES);
  crypto_scalarmult_base(pk, secretKey);
  return {publicKey: pk, secretKey: new Uint8Array(secretKey)};
};

nacl.box.publicKeyLength = crypto_box_PUBLICKEYBYTES;
nacl.box.secretKeyLength = crypto_box_SECRETKEYBYTES;
nacl.box.sharedKeyLength = crypto_box_BEFORENMBYTES;
nacl.box.nonceLength = crypto_box_NONCEBYTES;
nacl.box.overheadLength = nacl.secretbox.overheadLength;

nacl.sign = function(msg, secretKey) {
  checkArrayTypes(msg, secretKey);
  if (secretKey.length !== crypto_sign_SECRETKEYBYTES)
    throw new Error('bad secret key size');
  var signedMsg = new Uint8Array(crypto_sign_BYTES+msg.length);
  crypto_sign(signedMsg, msg, msg.length, secretKey);
  return signedMsg;
};

nacl.sign.open = function(signedMsg, publicKey) {
  checkArrayTypes(signedMsg, publicKey);
  if (publicKey.length !== crypto_sign_PUBLICKEYBYTES)
    throw new Error('bad public key size');
  var tmp = new Uint8Array(signedMsg.length);
  var mlen = crypto_sign_open(tmp, signedMsg, signedMsg.length, publicKey);
  if (mlen < 0) return null;
  var m = new Uint8Array(mlen);
  for (var i = 0; i < m.length; i++) m[i] = tmp[i];
  return m;
};

nacl.sign.detached = function(msg, secretKey) {
  var signedMsg = nacl.sign(msg, secretKey);
  var sig = new Uint8Array(crypto_sign_BYTES);
  for (var i = 0; i < sig.length; i++) sig[i] = signedMsg[i];
  return sig;
};

nacl.sign.detached.verify = function(msg, sig, publicKey) {
  checkArrayTypes(msg, sig, publicKey);
  if (sig.length !== crypto_sign_BYTES)
    throw new Error('bad signature size');
  if (publicKey.length !== crypto_sign_PUBLICKEYBYTES)
    throw new Error('bad public key size');
  var sm = new Uint8Array(crypto_sign_BYTES + msg.length);
  var m = new Uint8Array(crypto_sign_BYTES + msg.length);
  var i;
  for (i = 0; i < crypto_sign_BYTES; i++) sm[i] = sig[i];
  for (i = 0; i < msg.length; i++) sm[i+crypto_sign_BYTES] = msg[i];
  return (crypto_sign_open(m, sm, sm.length, publicKey) >= 0);
};

nacl.sign.keyPair = function() {
  var pk = new Uint8Array(crypto_sign_PUBLICKEYBYTES);
  var sk = new Uint8Array(crypto_sign_SECRETKEYBYTES);
  crypto_sign_keypair(pk, sk);
  return {publicKey: pk, secretKey: sk};
};

nacl.sign.keyPair.fromSecretKey = function(secretKey) {
  checkArrayTypes(secretKey);
  if (secretKey.length !== crypto_sign_SECRETKEYBYTES)
    throw new Error('bad secret key size');
  var pk = new Uint8Array(crypto_sign_PUBLICKEYBYTES);
  for (var i = 0; i < pk.length; i++) pk[i] = secretKey[32+i];
  return {publicKey: pk, secretKey: new Uint8Array(secretKey)};
};

nacl.sign.keyPair.fromSeed = function(seed) {
  checkArrayTypes(seed);
  if (seed.length !== crypto_sign_SEEDBYTES)
    throw new Error('bad seed size');
  var pk = new Uint8Array(crypto_sign_PUBLICKEYBYTES);
  var sk = new Uint8Array(crypto_sign_SECRETKEYBYTES);
  for (var i = 0; i < 32; i++) sk[i] = seed[i];
  crypto_sign_keypair(pk, sk, true);
  return {publicKey: pk, secretKey: sk};
};

nacl.sign.publicKeyLength = crypto_sign_PUBLICKEYBYTES;
nacl.sign.secretKeyLength = crypto_sign_SECRETKEYBYTES;
nacl.sign.seedLength = crypto_sign_SEEDBYTES;
nacl.sign.signatureLength = crypto_sign_BYTES;

nacl.hash = function(msg) {
  checkArrayTypes(msg);
  var h = new Uint8Array(crypto_hash_BYTES);
  crypto_hash(h, msg, msg.length);
  return h;
};

nacl.hash.hashLength = crypto_hash_BYTES;

nacl.verify = function(x, y) {
  checkArrayTypes(x, y);
  // Zero length arguments are considered not equal.
  if (x.length === 0 || y.length === 0) return false;
  if (x.length !== y.length) return false;
  return (vn(x, 0, y, 0, x.length) === 0) ? true : false;
};

nacl.setPRNG = function(fn) {
  randombytes = fn;
};

(function() {
  // Initialize PRNG if environment provides CSPRNG.
  // If not, methods calling randombytes will throw.
  var crypto = typeof self !== 'undefined' ? (self.crypto || self.msCrypto) : null;
  if (crypto && crypto.getRandomValues) {
    // Browsers.
    var QUOTA = 65536;
    nacl.setPRNG(function(x, n) {
      var i, v = new Uint8Array(n);
      for (i = 0; i < n; i += QUOTA) {
        crypto.getRandomValues(v.subarray(i, i + Math.min(n - i, QUOTA)));
      }
      for (i = 0; i < n; i++) x[i] = v[i];
      cleanup(v);
    });
  } else if (typeof require !== 'undefined') {
    // Node.js.
    crypto = require('crypto');
    if (crypto && crypto.randomBytes) {
      nacl.setPRNG(function(x, n) {
        var i, v = crypto.randomBytes(n);
        for (i = 0; i < n; i++) x[i] = v[i];
        cleanup(v);
      });
    }
  }
})();

})(typeof module !== 'undefined' && module.exports ? module.exports : (self.nacl = self.nacl || {}));


// Cloudflare Worker —— 成员自助接入。
// 主通道：手机 + 短信验证码登录平台 → 拿 MUSIC_U。
// 手动登记：成员直接粘贴浏览器里的 MUSIC_U（短信收不到 / 登录失败时用）。
// 两通道都：解析分享链接拿 song id → 用 KV 维护主账号池 → 重算分片 → 覆盖写 GitHub Secrets(NB_POOL_1..5)。
// 需要的 CF 环境变量/绑定：
//   GH_TOKEN   有 repo 权限的 GitHub PAT（写 secret 用，仅服务端，不落前端）
//   GH_OWNER   仓库 owner（如 xm921018）
//   GH_REPO    仓库名（如 cron-relay）
//   GROUP_PASS 一群群口令（群内共享的一个暗号，防外人乱加；不是逐人邀请码）
//   ⚠️ 本文件是「定制版」独立 worker（脚本名 dingzhi，地址 dingzhi.listenmusic888.workers.dev），
//      由 worker.js 复制派生：页面显示"定制版"、无群口令、登记固定按二群闸口（POOL_LIMIT_G2）计数。
//      与主 worker 共用同一个 KV 账号池（POOL 绑定）。改主 worker.js 逻辑时需手动同步本文件！
//   POOL_LIMIT 旧的单池上限键（已由 POOL_LIMIT_G1 / POOL_LIMIT_G2 取代，保留兼容）
//   POOL_LIMIT_G1 一群登记上限 / POOL_LIMIT_G2 二群登记上限（定制版默认 500，2026-10-22 上调 1500 的只有协同版）
//   POOL       KV namespace 绑定（维护主账号池，cookie 不落 GitHub 仓库文件）
// 注意：cookie 只在 KV 与 GitHub Secrets（加密）中存在，仓库文件无明文。


const BASE = 'https://music.163.com';
const NONCE = '0CoJUm6Qyw8W8jud';
const SECRET = 'TA3YiYCfY2dDJQgg';
const VI = '0102030405060708';
const ENCSEC = '84ca47bca10bad09a6b04c5c927ef077d9b9f1e37098aa3eac6ea70eb59df0aa28b691b7e75e4f1f9831754919ea784c8f74fbfadf2898b0be17849fd656060162857830e241aba44991601f137624094c114ea8d17bce815b0cd4e5b8e2fbaba978c6d1d14dc3d1faf852bdd28818031ccdaaa13a6018e1024e2aae98844210';

const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148';

// ---- base64 ----
const b64enc = (u8) => btoa(String.fromCharCode(...new Uint8Array(u8)));
const b64dec = (s) => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const utf8 = (s) => new TextEncoder().encode(s);

// ---- AES-CBC (WebCrypto) ----
async function aesCbc(dataU8, keyStr) {
  const key = await crypto.subtle.importKey('raw', utf8(keyStr), { name: 'AES-CBC' }, false, ['encrypt']);
  const n = 16 - dataU8.length % 16;
  const pad = new Uint8Array(dataU8.length + n);
  pad.set(dataU8); pad.fill(n, dataU8.length);
  const ct = await crypto.subtle.encrypt({ name: 'AES-CBC', iv: utf8(VI) }, key, pad);
  return new Uint8Array(ct);
}
// weapi 标准实现（2026-10-10 实测修复）：
//   json → AES(NONCE) → base64 → AES(随机16字符key) → base64 = params
//   encSecKey = RSA(随机key 反转后按 ASCII 转 hex, e=010001) 转 hex 补零到 256 位
// 旧实现漏了中间 base64 且 encSecKey 固定不匹配，导致平台解不开、返回空 200。
const RSA_MODULUS = '00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7';
function modPow(b, e, m) { let r = 1n; b %= m; while (e > 0n) { if (e & 1n) r = r * b % m; b = b * b % m; e >>= 1n; } return r; }
async function weapi(data) {
  const chars = '0123456789abcdef';
  const rnd = [...crypto.getRandomValues(new Uint8Array(16))].map(x => chars[x % 16]).join('');
  let p = await aesCbc(utf8(JSON.stringify(data)), NONCE);
  p = b64enc(p);
  p = await aesCbc(utf8(p), rnd);
  const rev = rnd.split('').reverse().join('');
  const hexOfAscii = [...rev].map(c => c.charCodeAt(0).toString(16).padStart(2, '0')).join('');
  const encSecKey = modPow(BigInt('0x' + hexOfAscii), 0x10001n, BigInt('0x' + RSA_MODULUS)).toString(16).padStart(256, '0');
  return { params: b64enc(p), encSecKey };
}

// 校验一个 MUSIC_U 是否还活着（手动登记即时反馈）
// 策略：重试 2 次；若平台接口不可达（网络/非 JSON 响应）且 cookie 形状合法，降级放行（provisional），
// 交由次日 Actions 的 login_by_cookie 复验，失效号会被 /api/report_dead 自动清理。
async function validateCookie(musicU) {
  const ck = 'MUSIC_U=' + musicU;
  let lastDiag = '';
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      // 普通接口（非 weapi）：带 cookie 直接查账号，2026-10-10 实测返回 JSON
      const r = await fetch(`${BASE}/api/nuser/account/get`, {
        method: 'GET',
        headers: { 'User-Agent': UA, Referer: BASE + '/', 'Cookie': ck },
      });
      const txt = await r.text();
      let j = null;
      try { j = JSON.parse(txt); } catch (e) {}
      if (j && j.code === 200 && (j.profile || {}).userId) return { ok: true, uid: j.profile.userId };
      if (j) return { ok: false, msg: 'MUSIC_U 无效或已失效（code=' + j.code + '，请重新从浏览器复制）' };
      lastDiag = 'HTTP ' + r.status + '，响应非 JSON：' + txt.slice(0, 60);
    } catch (e) {
      lastDiag = '网络异常：' + ((e && e.message) || e);
    }
    if (attempt < 2) await new Promise(res => setTimeout(res, 800));
  }
  if (/^[0-9a-fA-F]{80,}$/.test(musicU)) {
    const hex = [...blake2b(utf8(musicU), 6)].map(b => b.toString(16).padStart(2, '0')).join('');
    return { ok: true, uid: Number('0x' + hex.slice(0, 12)) % 1e12, provisional: true, diag: lastDiag };
  }
  return { ok: false, msg: '校验失败：' + lastDiag + '；且 cookie 形状不对，请重新从浏览器复制 MUSIC_U' };
}

async function resolveSong(link) {
  // 容错：成员经常把 APP 分享的整段文字（带歌名/emoji/@）直接粘进来，先提取出里面的第一个 URL
  const picked = link.match(/https?:\/\/[^\s"'《》<>，,）)】]+/);
  let url = (picked ? picked[0] : link).trim();
  // 先在【原链接】上提取 id：平台 APP 分享出来的单曲链接是 SPA 格式
  // music.163.com/#/song?id=xxx，井号后是 URL fragment，HTTP 请求不发送 fragment，
  // fetch 之后的 r.url 会把 id 一起丢掉，所以必须在 fetch 之前匹配
  // （网页版复制的 song?id= 格式、短链重定向后的 URL 同样兼容）
  let m = url.match(/[?&]id=(\d+)/);
  // 只收单曲：歌单/专辑/电台/节目/排行榜链接一律拒绝（防一个链接带出整张歌单）
  const COLLECT = /\/(playlist|album|radio|program|toplist|djradio|artist|mv)\b/i;
  if (COLLECT.test(url)) {
    return { ok: false, msg: '只收单曲链接：专辑 / 歌单 / 电台 / 排行榜 / MV 都不能登记。请在网易云 APP 里打开【那首歌】→ 分享 → 复制链接' };
  }
  let diag = '';
  try {
    const r = await fetch(url, { redirect: 'follow', headers: { 'User-Agent': UA } });
    url = r.url;
  } catch (e) {
    diag = 'fetch 异常：' + ((e && e.message) || e);
  }
  // 2026-11-12：短链解析兜底。此前 fetch 抛错被静默吞掉、或 163cn.tv 对数据中心请求
  // 不回 302 时，url 停在短链上 → 误报「链接里没找到歌曲 id」（hz bkNIU2s2 实测）。
  // 补：重试一次 follow + manual 模式直读 Location 头，报错时附带诊断信息。
  if (!m) m = url.match(/[?&]id=(\d+)/);
  if (!m) {
    await new Promise(res => setTimeout(res, 800));
    try {
      const r = await fetch(url, { redirect: 'follow', headers: { 'User-Agent': UA } });
      url = r.url;
    } catch (e) {
      diag = diag || ('重试 fetch 异常：' + ((e && e.message) || e));
    }
  }
  if (!m) {
    try {
      const r2 = await fetch(url, { redirect: 'manual', headers: { 'User-Agent': UA } });
      const loc = r2.headers.get('location') || '';
      if (loc) {
        url = loc;
        m = loc.match(/[?&]id=(\d+)/);
        if (!m) diag = 'Location 无 id：' + loc.slice(0, 80);
      } else {
        diag = diag || ('未返回 Location，HTTP ' + r2.status);
      }
    } catch (e) {
      diag = diag || ('manual fetch 异常：' + ((e && e.message) || e));
    }
  }
  if (COLLECT.test(url)) {
    return { ok: false, msg: '只收单曲链接：专辑 / 歌单 / 电台 / 排行榜 / MV 都不能登记。请在网易云 APP 里打开【那首歌】→ 分享 → 复制链接' };
  }
  // 原链接没带 id（如 163cn.tv 短链）时，用跟随重定向后的 r.url 兜底匹配一次
  if (!m) m = url.match(/[?&]id=(\d+)/);
  if (!m) return { ok: false, msg: '链接里没找到歌曲 id：识别到 ' + url.slice(0, 80) + (diag ? '（诊断：' + diag + '）' : '') + '。请在网易云 APP 里点「分享→复制链接」，把 http 开头的完整链接粘过来' };
  // 双保险：调平台歌曲详情接口确认这个 id 确实是一首歌（防歌单/电台 id 伪装混入）
  try {
    const r = await fetch(`${BASE}/api/song/detail?id=${m[1]}&ids=%5B${m[1]}%5D`, { headers: { 'User-Agent': UA, Referer: BASE + '/' } });
    const j = await r.json();
    if (!j || !Array.isArray(j.songs) || !j.songs.length) {
      return { ok: false, msg: '这个链接不是单曲（可能是歌单/电台/专辑 id）。请分享【单曲】：APP 里播放那首歌 → 分享 → 复制链接' };
    }
  } catch (e) {
    // 详情接口偶发异常时放行（歌单类 URL 已在上面被路径检查拦截）
  }
  return { ok: true, song: Number(m[1]) };
}

// ---- GitHub Secrets（sealed box） ----
// GH_TOKEN / GROUP_PASS 存于 KV（加密、不落仓库、不暴露给前端），运行时从 POOL 读取。
// 这样无需 Cloudflare Secret 权限即可配置，且 GitHub PAT 也不会进公开仓库文件。
let _cfg, _cfgAt = 0;
// KV 值防御性清洗：防止当初写入口令/token 时把 JSON 引号/空白一起存进去
const cleanKV = s => (s || '').trim().replace(/^"+|"+$/g, '');
async function cfg() {
  // 带 5 分钟 TTL 的缓存（2026-10-13 修复：此前永久缓存，KV 里轮换 GH_TOKEN/群口令后
  // 要等 isolate 重启才生效）
  if (!_cfg || Date.now() - _cfgAt > 300000) {
    _cfg = {
      ghToken: cleanKV(await POOL.get('GH_TOKEN')),
      groupPass: cleanKV(await POOL.get('GROUP_PASS')),
      adminPass: cleanKV(await POOL.get('ADMIN_PASS')),
      // 2026-11-11 v2.12：号池查看（/api/pool）认控制台满权/只读码（与主群同口径，KV 里
      // CONSOLE_PASS / CONSOLE_RO_PASS 已同步写入同值）。只加读、不加写。
      consolePass: cleanKV(await POOL.get('CONSOLE_PASS')),
      consoleRoPass: cleanKV(await POOL.get('CONSOLE_RO_PASS')),
      // 分配接口独立口令（2026-10-22）：/api/assign 会下发明文 CK，绝不能用群口令（定制版群口令
      // 就是协同版的对穿口令，泄露面更大）。未配置时该接口直接拒绝服务。
      assignPass: cleanKV(await POOL.get('ASSIGN_PASS')),
      // 分群上限：一群默认 200 / 二群默认 500；旧键 POOL_LIMIT 保留但不再参与闸门
      // 定制版保持 500 不变（2026-10-22：上调只给协同版；本群 isG2 恒 true，走 poolLimitG2）
      poolLimit: parseInt(cleanKV(await POOL.get('POOL_LIMIT')), 10) || 500,
      poolLimitG1: parseInt(cleanKV(await POOL.get('POOL_LIMIT_G1')), 10) || 500,
      poolLimitG2: parseInt(cleanKV(await POOL.get('POOL_LIMIT_G2')), 10) || 500,
      owner: GH_OWNER,
      repo: GH_REPO,
    };
    _cfgAt = Date.now();
  }
  return _cfg;
}
const GH = async () => { const c = await cfg(); return { token: c.ghToken, owner: c.owner, repo: c.repo }; };
// ---- 群口令校验（定制版：无口令，一律放行）----
// 定制版页面不带群口令（用户明确要求），服务端不再校验 pass；
// 归属固定走二群闸口（见下方 isG2 = true），上限 POOL_LIMIT_G2（定制版默认 500）。
function groupPassCheck(c, body) {
  return { ok: true };
}
// 危险管理接口的口令校验（2026-10-26 收紧，与协同版一致）。
// /api/report_dead 能按名单删号（带 confirm 直接删）、/api/resync 能强制重推 Secrets，
// 原来只认 GROUP_PASS（= 发给全体成员的群口令，还硬编码在客户端里）。
// 新口径：配了 ADMIN_PASS 就【只】认 ADMIN_PASS；没配时才退回群口令（老部署兼容）。
function adminPassOk(c, pass) {
  const p = String(pass || '');
  if (c.adminPass) return p === c.adminPass;
  return !!(c.groupPass && p === c.groupPass);
}
// 跨群对穿口令（2026-10-26）：KV 键 PEER_KEY，两群存同一个 32 位随机值。
// 原来对穿直接复用群口令（本群的 PEER_PASS 键里就是主群口令），
// 于是「群口令」既能登记、又能读本群全池（含邮箱）、还能删改号。配了 PEER_KEY 就只认它。
async function peerKey() { return cleanKV(await POOL.get('PEER_KEY')); }
async function peerPassOk(pass) {
  const k = await peerKey();
  const p = String(pass || '');
  if (k) return p === k;
  const old = cleanKV(await POOL.get('PEER_PASS'));
  return !!(old && p === old);
}
// ---- 分群计数辅助：历史条目没有 grp 字段的一律算一群 ----
const grpOf = e => (Number(e && e.grp) === 2 ? 2 : 1);
const groupLimitOf = (c, isG2) => (isG2 ? c.poolLimitG2 : c.poolLimitG1);
// 满员闸口的计数口径（2026-10-26 修复，与协同版保持一致）：排除「已过期但还没被 pruneExpired 清掉」
// 的号。这些号到期后已不参与轮转，却仍然占着人数上限，导致满员提示比实际可登记名额早出现。
function activePoolSize(arr, today) {
  const t = today || beijingDate();
  let n = 0;
  for (const e of (arr || [])) {
    const x = String((e && e.exp) || '').trim();
    if (!x || x === 'forever') { n++; continue; }
    if (/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(x) && x < t) continue;
    n++;
  }
  return n;
}
async function ghPublicKey() {
  const g = await GH();
  const r = await fetch(`https://api.github.com/repos/${g.owner}/${g.repo}/actions/secrets/public-key`, { headers: { Authorization: `token ${g.token}`, Accept: 'application/vnd.github+json', 'User-Agent': 'cron-relay-worker' } });
  return r.json();
}
// ---- blake2b (RFC 7693, BigInt 实现) ----
// GitHub Secrets API 要求 libsodium sealed box 格式：ephPub(32) || box(msg, nonce=blake2b24(ephPub||recipPub))
// 原实现缺临时公钥且 nonce 为零，是错的，任何密钥都写不进去。
const BLAKE2B_IV = [
  0x6a09e667f3bcc908n, 0xbb67ae8584caa73bn, 0x3c6ef372fe94f82bn, 0xa54ff53a5f1d36f1n,
  0x510e527fade682d1n, 0x9b05688c2b3e6c1fn, 0x1f83d9abfb41bd6bn, 0x5be0cd19137e2179n,
];
const BLAKE2B_SIGMA = [
  0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
  14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3,
  11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4,
  7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8,
  9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13,
  2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9,
  12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11,
  13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10,
  6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5,
  10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0,
];

function blake2b(input, outlen) {
  const MASK = (1n << 64n) - 1n;
  const rotr = (x, n) => ((x >> BigInt(n)) | (x << BigInt(64 - n))) & MASK;
  const G = (v, a, b, c, d, x, y) => {
    v[a] = (v[a] + v[b] + x) & MASK;
    v[d] = rotr(v[d] ^ v[a], 32);
    v[c] = (v[c] + v[d]) & MASK;
    v[b] = rotr(v[b] ^ v[c], 24);
    v[a] = (v[a] + v[b] + y) & MASK;
    v[d] = rotr(v[d] ^ v[a], 16);
    v[c] = (v[c] + v[d]) & MASK;
    v[b] = rotr(v[b] ^ v[c], 63);
  };
  let h = BLAKE2B_IV.slice();
  h[0] ^= BigInt(outlen) | 0x01010000n;   // 无 key 的参数块
  const total = input.length;
  const nb = Math.max(1, Math.ceil(total / 128));
  const dv = new DataView(new ArrayBuffer(8));
  for (let i = 0; i < nb; i++) {
    const blk = new Uint8Array(128);
    blk.set(input.subarray(i * 128, (i + 1) * 128));
    const isLast = i === nb - 1;
    const t = BigInt(isLast ? total : (i + 1) * 128);
    // 消息字 m[0..15]，小端 64 位
    const m = [];
    for (let j = 0; j < 16; j++) {
      let w = 0n;
      for (let k = 7; k >= 0; k--) w = (w << 8n) | BigInt(blk[j * 8 + k]);
      m.push(w);
    }
    const v = new Array(16);
    for (let j = 0; j < 8; j++) v[j] = h[j];
    for (let j = 0; j < 8; j++) v[8 + j] = BLAKE2B_IV[j];
    v[12] ^= t;
    if (isLast) v[14] = ~v[14] & MASK;
    for (let r = 0; r < 12; r++) {
      const s = (r % 10) * 16;
      G(v, 0, 4, 8, 12, m[BLAKE2B_SIGMA[s]], m[BLAKE2B_SIGMA[s + 1]]);
      G(v, 1, 5, 9, 13, m[BLAKE2B_SIGMA[s + 2]], m[BLAKE2B_SIGMA[s + 3]]);
      G(v, 2, 6, 10, 14, m[BLAKE2B_SIGMA[s + 4]], m[BLAKE2B_SIGMA[s + 5]]);
      G(v, 3, 7, 11, 15, m[BLAKE2B_SIGMA[s + 6]], m[BLAKE2B_SIGMA[s + 7]]);
      G(v, 0, 5, 10, 15, m[BLAKE2B_SIGMA[s + 8]], m[BLAKE2B_SIGMA[s + 9]]);
      G(v, 1, 6, 11, 12, m[BLAKE2B_SIGMA[s + 10]], m[BLAKE2B_SIGMA[s + 11]]);
      G(v, 2, 7, 8, 13, m[BLAKE2B_SIGMA[s + 12]], m[BLAKE2B_SIGMA[s + 13]]);
      G(v, 3, 4, 9, 14, m[BLAKE2B_SIGMA[s + 14]], m[BLAKE2B_SIGMA[s + 15]]);
    }
    for (let j = 0; j < 8; j++) h[j] = (h[j] ^ v[j] ^ v[j + 8]) & MASK;
  }
  // 输出小端 64 位字，截断到 outlen
  const out = new Uint8Array(outlen);
  let o = 0;
  for (let j = 0; j < 8 && o < outlen; j++) {
    dv.setBigUint64(0, h[j], true);
    const tmp = new Uint8Array(dv.buffer);
    for (let k = 0; k < 8 && o < outlen; k++) out[o++] = tmp[k];
  }
  return out;
}

// ---- libsodium sealed box ----
function sealBox(msgU8, theirPub) {
  const eph = nacl.box.keyPair();
  const seed = new Uint8Array(64);
  seed.set(eph.publicKey, 0);
  seed.set(theirPub, 32);
  const nonce = blake2b(seed, 24);
  const boxed = nacl.box(msgU8, nonce, theirPub, eph.secretKey);
  const out = new Uint8Array(32 + boxed.length);
  out.set(eph.publicKey, 0);
  out.set(boxed, 32);
  return out;
}

async function ghPutSecret(name, value) {
  const g = await GH();
  const pk = await ghPublicKey();
  if (!pk || !pk.key || !pk.key_id) throw new Error('获取 GitHub Secrets 公钥失败（GH_TOKEN 无效/过期或仓库不对）：' + JSON.stringify(pk).slice(0, 120));
  const theirPub = b64dec(pk.key);
  const sealed = sealBox(utf8(value), theirPub);
  const r = await fetch(`https://api.github.com/repos/${g.owner}/${g.repo}/actions/secrets/${name}`, {
    method: 'PUT',
    headers: { Authorization: `token ${g.token}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json', 'User-Agent': 'cron-relay-worker' },
    body: JSON.stringify({ encrypted_value: b64enc(sealed), key_id: pk.key_id }),
  });
  // 2026-10-22 加固：此前返回 status 但调用方不检查，422（值超 48KB）等失败被静默吞掉，
  // 导致最大分片连续 4 天写不进去没人发现。现在非 2xx 直接抛错让登记/resync 显式失败。
  // 2026-10-22 二次修复：Secret 写入成功时 GitHub 可能返回 201（新建）也可能是 204（更新）。
  // 只认 200/201 会把 204 判成失败 → pushPool 写完 NB_POOL_1 就抛错，后面 11 个槽位留着旧值，
  // 结果是账号池被切成「新一片 + 旧十一 片」，比写不进去更危险。改为 2xx 一律算成功。
  if (!r.ok) {
    throw new Error(`写入 Secret ${name} 失败 HTTP ${r.status}（值过大或 GH_TOKEN 无权限）`);
  }
  return r.status;
}

// ---- 分片写回 NB_POOL_*（片数按号池体积自动伸缩，见 pushPool）----
// added 统一按北京时间记（2026-10-13 修复：此前用 UTC，北京 0-8 点登记的号会被提前一天入池，
// 与 run.py 的北京时间口径不一致）
function beijingDate() {
  return new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10);
}
// 2026-10-30：入池时间精确到秒（北京时间，与 cron-relay 同口径，两群共用一个 D1）
function beijingDateTime() {
  return new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 19).replace('T', ' ');
}
// ---- 有效期（exp）：'YYYY-MM-DD' 到期即移除；无 exp / 'forever' = 永久 ----
function isExpiredEntry(e) {
  return !!(e && e.exp && e.exp !== 'forever' && String(e.exp) < beijingDate());
}
// 2026-10-29：单列 exp 的到期判定（给 D1 查重结果 / KV 回退路径用）
function isExpiredExp(exp) {
  return !!(exp && exp !== 'forever' && String(exp) < beijingDate());
}
function expDaysLeft(e) {
  if (!e || !e.exp || e.exp === 'forever') return Infinity;
  return Math.round((new Date(e.exp + 'T00:00:00Z') - new Date(beijingDate() + 'T00:00:00Z')) / 86400000);
}
function isSoonExpired(e) {
  const d = expDaysLeft(e);
  return d !== Infinity && d <= 3;
}
function beijingDatePlus(n) {
  return new Date(Date.now() + 8 * 3600 * 1000 + n * 86400 * 1000).toISOString().slice(0, 10);
}
function parseExpInput(x) {
  if (x == null || String(x).trim() === '') return { ok: true };
  const s = String(x).trim();
  if (s === 'forever' || s === '永久') return { ok: true, exp: 'forever' };
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return { ok: true, exp: s };
  if (/^\d{1,4}$/.test(s)) return { ok: true, exp: beijingDatePlus(parseInt(s, 10)) };
  return { ok: false };
}

// ====================================================================
// 客服标签 / 套餐档位（2026-10-27 新增，与 cron-relay 同一套实现、同一份配置）
// 配置存 D1 kv_misc k='reg_cfg'：两群共用同一个 D1 库，所以只维护一份，两个 worker 读到的完全一致。
// accounts.agent = 客服名字原文；accounts.plan = 登记时买的套餐显示名（1年/2年/永久）。
// ====================================================================
const REG_CFG_KEY = 'reg_cfg';
const REG_CFG_KV = 'REG_CFG';
const REG_CFG_DEFAULT = {
  agents: ['徐'],
  // 2026-10-27：加「1月」（30 天）档。档位顺序 = 客户端下拉顺序，从短到长排。
  // 2026-11-05：加 price（单价·元），与 cron-relay 同一套。记账（ledger）靠它算金额；
  //             缺省按 -1「未定价」处理，不是 0 —— 0 会被结算当成免费，整档收入凭空消失。
  plans: [
    { key: '1m', label: '1月', days: 30, price: 3 },
    { key: '6m', label: '半年', days: 180, price: 10 },
    { key: '1y', label: '1年', days: 365, price: 15 },
    { key: '2y', label: '2年', days: 730, price: 20 },
    { key: 'forever', label: '永久', days: 0, price: 80 },
  ],
};

// 不校验是否在名单内：名单随时会改，旧客户端可能还在提交已删掉的名字，直接拒绝会让登记全线失败
function normAgent(x) {
  return String(x == null ? '' : x).replace(/[\u0000-\u001f\u007f"'<>]/g, '').trim().slice(0, 16);
}

/* 2026-11-09：邮箱校验（与主群 worker 同一套，两边报错话术一致）。
   原来只做 /^[^\s@]+@[^\s@]+\.[^\s@]+$/，实测池里有 @qq.con / @qq.cpm / @qq,com 这种，
   格式全放过、SMTP 必然失败，队列却照样标 sent，号主收不到任何提醒。
   返回空串 = 合法，否则返回直接给用户看的中文原因。 */
const EMAIL_TLD_TYPO = { con: 'com', cpm: 'com', ocm: 'com', comn: 'com', comm: 'com', cmo: 'com', cim: 'com', nte: 'net', ntei: 'net', orgg: 'org' };
function emailBad(x) {
  const s = String(x == null ? '' : x).trim();
  if (!s) return '请填写常用邮箱';
  if (s.length > 120) return '邮箱太长了，请检查一下';
  if (/[\s,，;；、]/.test(s)) return '邮箱里有多余的空格或逗号，请只填 name@example.com 这一串';
  const m = s.match(/^([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+)\.([A-Za-z]{2,8})$/);
  if (!m) return '邮箱格式不对，请填成 name@example.com 这样';
  if ((m[2] + '.' + m[3]).indexOf('..') >= 0) return '邮箱域名里有连续的句点，请检查一下';
  const tld = m[3].toLowerCase();
  if (EMAIL_TLD_TYPO[tld]) return '邮箱后缀好像写错了（' + tld + ' → ' + EMAIL_TLD_TYPO[tld] + '？），请确认后再提交';
  return '';
}

function normRegCfg(o) {
  const out = { agents: [], plans: [] };
  const src = (o && typeof o === 'object') ? o : {};
  for (const a of (Array.isArray(src.agents) ? src.agents : [])) {
    const v = normAgent(a);
    if (v && !out.agents.includes(v)) out.agents.push(v);
  }
  for (const p of (Array.isArray(src.plans) ? src.plans : [])) {
    if (!p || typeof p !== 'object') continue;
    const label = String(p.label || '').trim().slice(0, 8);
    if (!label) continue;
    const days = Math.max(0, Math.min(36500, parseInt(p.days, 10) || 0));
    const key = String(p.key || label).trim().slice(0, 16) || label;
    if (out.plans.some(x => x.key === key)) continue;
    // 2026-11-05：单价（元）。缺省/非法 = -1（未定价），不是 0。
    // 老配置（11-05 之前存的 reg_cfg）里没有 price 字段 → 按内置默认价同名档位兜底，
    // 否则升级的那一刻整群档位会一起变「未定价」，记账全是待补价。
    let price = Number(p.price);
    if (p.price === undefined || p.price === null || String(p.price).trim() === ''
        || !isFinite(price) || price < 0) {
      const dft = REG_CFG_DEFAULT.plans.find(x => x.label === label);
      price = dft ? dft.price : -1;
    }
    price = Math.round(price * 100) / 100;
    out.plans.push({ key: key, label: label, days: days, price: price });
  }
  if (!out.agents.length) out.agents = REG_CFG_DEFAULT.agents.slice();
  if (!out.plans.length) out.plans = REG_CFG_DEFAULT.plans.map(p => ({ key: p.key, label: p.label, days: p.days, price: p.price }));
  return out;
}

// 档位单价（元）。返回 -1 = 未定价（结算页单列「待补价」，绝不当 0 元）。
function planPrice(cfg, label) {
  const s = String(label == null ? '' : label).trim();
  if (!s) return -1;
  const p = ((cfg && cfg.plans) || []).find(it => it.key === s || it.label === s);
  if (!p) return -1;
  return (typeof p.price === 'number' && p.price >= 0) ? p.price : -1;
}

async function regCfg() {
  let raw = null;
  if (d1ok()) {
    try {
      const rows = await d1All('SELECT v FROM kv_misc WHERE k=?', [REG_CFG_KEY]);
      if (rows && rows.length) raw = rows[0].v;
    } catch (e) { console.error('读 reg_cfg(D1) 失败:', e && e.message); }
  }
  if (!raw) {
    try { raw = await POOL.get(REG_CFG_KV); } catch (e) {}
  }
  let o = null;
  try { o = raw ? JSON.parse(raw) : null; } catch (e) { o = null; }
  return normRegCfg(o);
}

// 把客户端传来的「套餐」（key 或显示名都认）解析成 {key,label,exp}
function planOf(cfg, x) {
  const s = String(x == null ? '' : x).trim();
  if (!s) return null;
  const p = (cfg.plans || []).find(it => it.key === s || it.label === s);
  if (!p) return null;
  // 2026-11-11：补 days（原始天数），join_manual 的「套餐与 exp 打架以套餐为准」兜底要用
  return { key: p.key, label: p.label, days: p.days, exp: (p.days > 0 ? beijingDatePlus(p.days) : 'forever') };
}
// 到期账号清理：删独立键 + 记墓碑 + 刷 master + 回推 GitHub Secrets（只在有过期时才写）
async function pruneExpired() {
  const master = await mergePool();
  const dead = master.filter(isExpiredEntry);
  if (!dead.length) return { master: master, count: 0 };
  // 读走 D1 后必须两边一起删：只删 KV 的话，下一次 mergePool 会从 D1 把过期号读回来。
  await Promise.all(dead.map(async e => {
    await POOL.delete(entryKeyOf(e));
    if (!(await d1Delete(e))) console.error('D1 过期删除失败:', e && (e.name || e.uid));
  }));
  try {
    const log = new Set(await getDeadLog());
    for (const e of dead) log.add(entryKeyOf(e));
    await POOL.put('dead_log', JSON.stringify([...log].slice(-500)));
  } catch (e) {}
  const kept = master.filter(e => !isExpiredEntry(e));
  await d1LogDead(dead, 'expired');
  // 2026-10-26：到期待清理也是「静默删号」（号池管理工具打开列表就会顺手清一批）。
  // 同样进通知队列：12 小时内重新登记（= 续费）→ 回池判定不发；没回来 → 发「账号信息过期」。
  try { for (const e of dead) await d1QueueNotice(e); } catch (e) { console.error('通知队列写入失败:', e && e.message); }
  // master 缓存不再回写（2026-10-22）：读者全走 D1，entry: 独立键才是权威
  await pushPool(kept);
  try { await refreshPoolSnap(); } catch (e) {}   // 号池变了 → 刷新单键应急快照
  return { master: kept, count: dead.length };
}

/* ============================================================================
   2026-11-09：CK 失效「超时自动清理」（与主群 cron-relay 的 worker 逐字同构）
   ----------------------------------------------------------------------------
   背景：删号前复核碰到「CK 死了、网易账号还在」只打 relogin_at + 发信，号留在库里；
   而 buildPlanFrom 把 relogin 号摘出听众环 ⇒ 客户端不再上报它 ⇒ 没有任何路径会再处理它。
   口径：relogin_at 非空且距今 ≥ RELOGIN_TTL_DAYS（KV 可配，默认 7 天）→ 删号 + 入队发信。
   删除链路照抄 report_dead：d1Delete 成功才算删 → 清 entry 键 / 墓碑 / 队列 / 流水 → 推池 + 刷快照。
   定时器：dz 的 worker 没有 scheduled handler（crons 为空），由主群 cron 通过
   POST /api/relogin_sweep（对穿口令）调用；也可手工调。
   ============================================================================ */
async function reloginTtlDays() {
  try {
    const v = Number(cleanKV(await POOL.get('RELOGIN_TTL_DAYS')));
    if (v > 0) return v;
  } catch (_e) {}
  return 7;
}

async function pruneStaleRelogin(days) {
  if (!d1ok()) return { ok: false, msg: 'D1 未绑定' };
  const ttl = Number(days) > 0 ? Number(days) : await reloginTtlDays();
  const cutoff = Date.now() - ttl * 86400000;
  // 读失败必须当失败（铁律 3c）：读不到不等于「没有超时号」，否则会静默永不清理。
  const rows = await d1All("SELECT uid,name,email,relogin_at FROM accounts WHERE pool=? AND relogin_at IS NOT NULL AND relogin_at<>''",
    [POOL_NAME]);
  if (!rows) return { ok: false, msg: 'D1 查询失败（accounts 读不到）' };
  const stale = rows.filter(r => {
    const t = Date.parse(String(r.relogin_at || ''));
    return !isNaN(t) && t <= cutoff;
  });
  if (!stale.length) return { ok: true, ttl: ttl, checked: rows.length, removed: 0, names: [] };

  const master = await mergePool();
  const gone = [], fail = [];
  for (const r of stale) {
    const full = master.find(e => String(e.uid || '') === String(r.uid || '')
                                  && (!r.name || String(e.name || '') === String(r.name)))
                 || { uid: r.uid, name: r.name, email: r.email };
    let ok = false;
    try { ok = (await d1Delete(full)) === true; } catch (_e) { ok = false; }
    (ok ? gone : fail).push(full);
  }
  await Promise.all(gone.map(async e => { try { await POOL.delete(entryKeyOf(e)); } catch (_e) {} }));
  const ekeys = gone.map(entryKeyOf);
  if (ekeys.length) {
    try {
      const log = new Set(await getDeadLog());
      for (const k of ekeys) log.add(k);
      await POOL.put('dead_log', JSON.stringify([...log].slice(-500)));
    } catch (_e) {}
  }
  let queued = 0;
  for (const e of gone) { try { if (await d1QueueNotice(e, 'relogin_timeout')) queued++; } catch (_e) {} }
  await d1LogDead(gone, 'cookie_invalid');
  const gs = new Set(ekeys);
  try { await pushPool(master.filter(e => !gs.has(entryKeyOf(e)))); } catch (_e) {}
  try { await refreshPoolSnap(); } catch (_e) {}
  const nmOf = e => e.name || String(e.uid || '');
  const names = gone.map(nmOf), failed = fail.map(nmOf);
  if (names.length || failed.length) {
    console.log('relogin 超时清理（TTL ' + ttl + ' 天）：检查 ' + rows.length + ' 个已通知号，删除 ' + names.length
      + (names.length ? '（' + names.join('、') + '）' : '')
      + (failed.length ? '，删除失败 ' + failed.length + ' 个下轮重试（' + failed.join('、') + '）' : ''));
  }
  return { ok: true, ttl: ttl, checked: rows.length, removed: names.length, queued: queued,
           names: names, failed: failed };
}
async function gzipU8(u8) {
  // 2026-10-22：分片 JSON 先 gzip 再 base64。此前直接 base64 JSON，分片 45000 字符
  // 封装后约 1.78 倍膨胀到 ~80KB，超过 GitHub Secret 48KB 上限 → 最大那片恒被 422
  // 拒绝（且空槽都成功，表面看 resync 正常），老账号变更自 10-18 起没进过 Actions 账号池。
  const cs = new CompressionStream('gzip');
  const stream = new Blob([u8]).stream().pipeThrough(cs);
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

// 2026-10-22：Secrets 分片降级为「只读回退备份」，默认不再随每次登记/删除重写。
// 原因：一次 pushPool = 12 次 ghPutSecret（每次 X25519 + sealed box + 加密 + PUT），
// 是整个 worker 最大的 CPU 消耗；而所有读者（run.py / make_accounts.py / run.yml plan）
// 现在都先走 D1（/api/assign、/api/pool_stat），只有 D1 完全不可用时才回退 Secrets。
// 紧急需要重推一份全量快照：KV 里把 PUSH_SECRETS 设为 '1'，或直接调 /api/resync（强制推）。
let _pushOn = null, _pushOnAt = 0;
async function pushPoolEnabled() {
  if (_pushOn !== null && Date.now() - _pushOnAt < 60000) return _pushOn;
  try { _pushOn = (cleanKV(await POOL.get('PUSH_SECRETS')) === '1'); }
  catch (e) { _pushOn = false; }
  _pushOnAt = Date.now();
  return _pushOn;
}

async function pushPool(entries, force) {
  if (!force && !(await pushPoolEnabled())) return { skipped: true, count: entries.length };
  const CHUNK_MAX = 40000;  // 单片原始 JSON 字符数；实测 gzip≈0.52 字节/字符（CK hex 不可压缩），b64+sealed 后 ~37KB < 48KB
  // 2026-11-01：片数不再写死 12。按号池实际体积自动算（ceil(总字符 / CHUNK_MAX)）：
  // 池子涨多少片就自动多写几片，读取端（run.py / make_accounts.py / run.yml plan）改成动态扫 env，
  // 两端都不需要再改代码。SLOT_MAX 只是「异常数据别把 GitHub API 打爆」的护栏，
  // 40 片 × 4 万字符 ≈ 160 万字符 ≈ 1700 号，远高于注册上限 1200，实际用不满。
  const SLOT_MAX = 40;
  const chunks = [];
  let cur = [];
  let size = 0;
  for (const e of entries) {
    const s = JSON.stringify(e).length + 1;
    if (size + s > CHUNK_MAX && cur.length) { chunks.push(cur); cur = []; size = 0; }
    cur.push(e); size += s;
  }
  if (cur.length) chunks.push(cur);
  if (chunks.length > SLOT_MAX) {
    const dropped = chunks.slice(SLOT_MAX).reduce((n, c) => n + c.length, 0);
    console.error(`号池 ${entries.length} 条超出 ${SLOT_MAX} 片 Secrets 容量，超出的 ${dropped} 条未写入，请扩容或清理！`);
  }
  const writeN = Math.min(chunks.length, SLOT_MAX);
  // 上次写了几片（KV POOL_SLOTS）。号池收缩时必须把高位槽写成 '[]' 清干净，
  // 否则读取端会把上一版遗留的高位分片也并进来（等于凭空多出一批旧号）。
  // 初值 12 = 改造前固定片数，保证第一次跑时能清掉 13..12 之外可能存在的残留。
  let prevN = 12;
  try {
    const p = parseInt(cleanKV(await POOL.get('POOL_SLOTS')) || '', 10);
    if (p > 0) prevN = p;
  } catch (e) {}
  const totalN = Math.max(writeN, prevN);
  for (let i = 0; i < totalN; i++) {
    const name = `NB_POOL_${i + 1}`;
    if (i < writeN) await ghPutSecret(name, b64enc(await gzipU8(utf8(JSON.stringify(chunks[i])))));
    else await ghPutSecret(name, b64enc(await gzipU8(utf8('[]'))));
  }
  try { await POOL.put('POOL_SLOTS', String(writeN)); } catch (e) {}
  return { slots: writeN, count: entries.length };
}

// ---- 账号池并发安全 ----
// 真实来源 = 每条账号一个独立 KV 键（entry: 前缀）。单键写入/删除互不干扰，从根上消除
// "整表读-改-写"竞态（此前多人同时登记会整表互相覆盖，表现为账号池条目凭空减少）。
// master 键降级为合并视图缓存：即使被并发写坏，下次 mergePool 会从独立键自动重建。
function entryKeyOf(e) {
  return e && e.uid != null && String(e.uid) !== ''
    ? 'entry:u' + String(e.uid)
    : 'entry:n' + encodeURIComponent(String((e && e.name) || 'unknown'));
}

// 删除墓碑：report_dead/管理删除过的账号键记录在 dead_log，防止
// ① master 边缘缓存旧快照（≤60s）把已删条目"复活"回填；
// ② 刚被清理的成员在缓存窗口内重新登记被误判"已登记"。重新登记成功后自动移除墓碑。
async function getDeadLog() {
  try { return JSON.parse(await POOL.get('dead_log') || '[]') || []; } catch (e) { return []; }
}

async function mergePool() {
  // 读走 D1：一条 SELECT 取代原来的「1 次 list + N 次 POOL.get」。
  // 账号池 213 个号时，这一步从 214 次 KV 读 / 214KB 传输降到 1 次 D1 查询。
  const d1 = await d1Pool();
  if (d1) return d1;
  return await mergePoolKV();
}

// 纯 KV 版合并（不做 D1 优先）。
// 用途：/api/d1_sync 必须拿「KV 的真实内容」去对齐 D1，走 mergePool 会变成 D1 对齐 D1，没有意义。
async function mergePoolKV() {
  // ① 单键快照优先（2026-10-22 第三批）：1 次 KV 读拿到全池。
  //    原来的「list + 逐键 get」在 1000+ 个号时超过单次 invocation 的 1000 次外部操作上限
  //    → 兜底路径必然失败，灾备形同虚设。
  try {
    const snap = await POOL.get(poolSnapKey());
    if (snap) {
      const arr = JSON.parse(snap);
      if (Array.isArray(arr) && arr.length) {
        const dead = new Set(await getDeadLog());
        return arr.filter(e => !dead.has(entryKeyOf(e)));
      }
    }
  } catch (e) { console.error('号池快照读取失败，回退 entry 键:', e && e.message); }

  // ② 没有快照 → 退回 entry: 独立键（真实来源），但必须限制读取条数：
  //    1 次 dead_log + 1~2 次 list + 最多 900 次 get < 1000（单次 invocation 外部操作上限）。
  const MAX_KEYS = 900;
  const keyNames = [];
  let cursor, truncated = false;
  do {
    const page = await POOL.list({ prefix: 'entry:', limit: 1000, cursor });
    for (const k of page.keys) {
      if (keyNames.length >= MAX_KEYS) { truncated = true; break; }
      keyNames.push(k.name);
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor && !truncated);
  if (truncated) console.error('KV 兜底：entry 键超过 ' + MAX_KEYS + ' 个，已截断（单次调用 1000 次外部操作上限）');
  // 2026-10-22：master 是 ~200KB 的旧合并缓存，以前每次都先读它再合并，等于每次回退都白传一次
  // 大对象 + 解析。只在「一个 entry: 键都读不到」的极端情况（首次迁移 / 键被误删）才读它兜底。
  let base = [];
  if (!keyNames.length) {
    try { base = JSON.parse(await POOL.get('master') || '[]') || []; } catch (e) {}
  }
  const deadLog = new Set(await getDeadLog());
  const byKey = new Map();
  for (const e of base) {
    if (deadLog.has(entryKeyOf(e))) continue;   // 墓碑内的缓存残留不参与（已删账号不复活）
    byKey.set(entryKeyOf(e), e);                // 顺带去重历史重复条目
  }
  const vals = await Promise.all(keyNames.map(n => POOL.get(n)));
  let changed = false;
  for (let i = 0; i < keyNames.length; i++) {
    if (!vals[i]) { changed = true; continue; }        // 键已删但 list 索引未收敛，跳过
    let v; try { v = JSON.parse(vals[i]); } catch (e) { continue; }
    if (!byKey.has(keyNames[i])) { byKey.set(keyNames[i], v); changed = true; }
  }
  const merged = [...byKey.values()];
  // 回填：master 有但独立键缺失的老数据（首次升级时一次性迁移，之后不再触发）
  const listed = new Set(keyNames);
  await Promise.all(merged
    .filter(e => !listed.has(entryKeyOf(e)))
    .map(e => POOL.put(entryKeyOf(e), JSON.stringify(e))));
  if (changed || merged.length !== base.length) {
    // master 缓存不再回写（2026-10-22）：读者全走 D1，entry: 独立键才是权威
  }
  return merged;
}

// 读全池，并保证包含「刚写入的那一条」。
// 用途：登记成功后要推 Secrets 分片，如果 D1 镜像写失败或读延迟，这个新号就会从分片里消失，
// 第二天日常/发动态就漏号。这里按主键再兜一次，成本只是一次字符串比较。
async function mergePoolEntry(entry, ekey) {
  const list = await mergePool();
  const k = ekey || entryKeyOf(entry);
  if (!list.some(e => entryKeyOf(e) === k)) list.push(entry);
  return list;
}

async function addEntry(entry) {
  // 有效期默认永久（定制版），管理端可随时修改（exp=YYYY-MM-DD，forever=永久）
  if (!entry.exp) entry.exp = 'forever';
  const ekey = entryKeyOf(entry);
  const uidKey = entry.uid != null ? String(entry.uid) : null;

  // ---- D1 快速路径：一次 SELECT 完成查重（原路径要把整个账号池的 entry 键全读一遍）----
  if (d1ok()) {
    // uid 为空的（用 name 占位的老号）只能按 name 查。不带 uid 时不要拼那个 ? 占位符，
    // 否则得传哨兵值，而 D1 绑定含 NUL 的字符串会报错 → 白走一次 KV 回退。
    // 2026-11-08：改为 d1FindDup（两条单条件查询，各走索引），实测从扫全池降到 1~2 行。
    const dup = await d1FindDup(uidKey, entry.name);
    if (dup === null) {
      console.error('D1 查重失败，回退 KV 全量查重');
    } else {
      // 2026-10-29：查重带上 exp —— 已过有效期的号允许重新登记（= 续费）。
      // 以前不看 exp 直接回「已登记过」，而定制版也没有任何地方清到期号 → 到期即无法再用。
      // 2026-11-08：dup 现在可能有两条（uid 一条 / name 一条），任意一条有效就拒绝。
      if (dup.length && dup.some(x => !isExpiredExp(x && x.exp))) {
        return { ok: false, msg: '该账号已登记过（每个账号限登记一首歌），无需重复登记。' };
      }
      if (dup.length) {
        // 过期覆盖：旧的 KV 键与 D1 行都清掉，避免「旧键按 name / 新键按 uid」并存两份。
        for (const k of [ekey,
                         ...dup.map(d => (d && d.uid != null) ? 'entry:u' + String(d.uid) : ''),
                         entry.name ? 'entry:n' + encodeURIComponent(String(entry.name)) : '']) {
          if (!k) continue;
          try { await POOL.delete(k); } catch (e) {}
        }
        if (uidKey) {
          try { await d1Run('DELETE FROM accounts WHERE pool=? AND (uid=? OR name=?)',
                            [POOL_NAME, uidKey, String(entry.name || '')]); } catch (e) {}
        } else {
          try { await d1Run('DELETE FROM accounts WHERE pool=? AND name=?',
                            [POOL_NAME, String(entry.name || '')]); } catch (e) {}
        }
        console.log('到期号重新登记（续费）:', String(entry.name || uidKey));
      }
      // KV 仍写一份：D1 万一回滚，KV 里必须是完整数据
      await POOL.put(ekey, JSON.stringify(entry));
      if (!(await d1Upsert(entry))) {
        console.error('D1 登记镜像失败（KV 已写入，可用 /api/resync 补齐）');
      }
      // 2026-11-05：落一笔记账流水（成交台账）。写失败只告警 —— 记账出错不能反过来让登记失败。
      try { await ledgerAdd(entry); } catch (e) { console.error('记账流水写入失败:', e && e.message); }
      // 重新登记 → 清墓碑（只影响 KV 回退路径）
      try {
        const deadLog = new Set(await getDeadLog());
        if (deadLog.size) {
          const cleared = [...deadLog].filter(k => k !== ekey
            && !(uidKey && k === 'entry:u' + uidKey)
            && !(entry.name && k === 'entry:n' + encodeURIComponent(String(entry.name))));
          if (cleared.length !== deadLog.size) await POOL.put('dead_log', JSON.stringify(cleared));
        }
      } catch (e) {}
      // 只有真要推 Secrets 时才做「全池 + 新号」合并（那是一次全表读）——
      // 默认关闭推送后，这里不该再为一份没人读的分片白跑一次查询。
      if (await pushPoolEnabled()) await pushPool(await mergePoolEntry(entry, ekey));
      try { await refreshPoolSnap(); } catch (e) {}
      return { ok: true };
    }
  }

  // ---- KV 回退路径（D1 未绑定或查询失败）----
  // 2026-10-29：与 D1 路径同口径 —— 已过有效期的旧登记不算「已登记过」，允许覆盖。
  const kvOld = await POOL.get(ekey);
  if (kvOld) {
    let oldExp = '';
    try { oldExp = (JSON.parse(kvOld) || {}).exp || ''; } catch (e) {}
    if (!isExpiredExp(oldExp)) {
      return { ok: false, msg: '该账号已登记过（每个账号限登记一首歌），无需重复登记。' };
    }
    try { await POOL.delete(ekey); } catch (e) {}
  }
  const deadLog = new Set(await getDeadLog());
  const master = await mergePool();
  const staleKeys = [];                        // 到期旧条目：允许被这次登记覆盖，稍后清掉
  for (const e of master) {
    if (deadLog.has(entryKeyOf(e))) continue;   // 墓碑内的是缓存残留（刚被清理），不算已登记
    const same = (uidKey && e.uid != null && String(e.uid) === uidKey)
      || (entry.name && e.name === entry.name);
    if (same && isExpiredExp(e && e.exp)) { staleKeys.push(entryKeyOf(e)); continue; }
    if (uidKey && e.uid != null && String(e.uid) === uidKey) {
      return { ok: false, msg: '该账号已登记过（每个账号限登记一首歌），无需重复登记。' };
    }
    if (entry.name && e.name === entry.name) {
      return { ok: false, msg: '该手机号/账号已登记过（每个账号限登记一首歌），无需重复登记。' };
    }
  }
  for (const k of staleKeys) { try { await POOL.delete(k); } catch (e) {} }
  if (staleKeys.length) console.log('到期号重新登记（续费，KV 路径）:', String(entry.name || uidKey));
  // 权威写入：只写自己的独立键，永远不会覆盖别人的登记
  await POOL.put(ekey, JSON.stringify(entry));
  try { await d1Upsert(entry); } catch (e) { console.error('D1 镜像失败:', e && e.message); }
  // 2026-11-05：记账流水（与 D1 路径同口径）。D1 已经不可用时这里也会是 no-op。
  try { await ledgerAdd(entry); } catch (e) { console.error('记账流水写入失败:', e && e.message); }
  if (deadLog.size) {
    const cleared = [...deadLog].filter(k => k !== ekey
      && !(uidKey && k === 'entry:u' + uidKey)
      && !(entry.name && k === 'entry:n' + encodeURIComponent(String(entry.name))));
    if (cleared.length !== deadLog.size) {
      try { await POOL.put('dead_log', JSON.stringify(cleared)); } catch (e) {}
    }
  }
  const updated = master.filter(e => staleKeys.indexOf(entryKeyOf(e)) < 0).concat([entry]);
  // master 缓存不再回写（2026-10-22）：读者全走 D1，entry: 独立键才是权威
  await pushPool(updated);
  // 本分支是「D1 查重失败」才走到：如果只是查询超时（D1 仍可写），这次快照能补上新号；
  // 真的未绑定时 refreshPoolSnap 自己会因 d1ok() 为假直接返回 false，不会抛错。
  try { await refreshPoolSnap(); } catch (e) {}
  return { ok: true };
}

// ====================================================================
// D1 账号池（2026-10-22 新增；KV 仍是唯一权威，D1 是影子库，双写 + 只读查询）
// 目的：
//   ① 让 run.py 直接问「我这一班该跑哪些号、每个号听哪几首」，彻底废掉
//      GitHub Secrets 分片（48KB 上限 / 槽位上限 500 / 半更新 三个问题一起消失）；
//   ② 每日轮转分配：听众集合每天 100% 更换，但每首歌每天恰好 p 个听众，一个都不漏。
// 约定：任何 D1 异常只 console.error，绝不抛出、绝不影响 KV 主流程。
// ====================================================================
const POOL_NAME = 'dz';        // 主群；dingzhi 版为 'dz'
const ASSIGN_TARGET = 30;      // 每首歌每天的目标听众数

function d1ok() {
  try { return typeof DB !== 'undefined' && DB && typeof DB.prepare === 'function'; } catch (e) { return false; }
}
async function d1All(sql, params) {
  if (!d1ok()) return null;
  try {
    const st = DB.prepare(sql);
    const r = params && params.length ? await st.bind(...params).all() : await st.all();
    return (r && r.results) || [];
  } catch (e) { console.error('D1 all 失败:', e && e.message); return null; }
}

// 死号流水写 D1（2026-10-22 新增）：KV 里的 dead_log 只是「墓碑名单」，最多 500 条、只存键名，
// 看不出是谁、什么时候、因为什么被清理。D1 dead_log 表存完整流水，供周报统计与事后追查。
async function d1LogDead(entries, reason) {
  if (!d1ok() || !entries || !entries.length) return;
  const at = new Date(Date.now() + 8 * 3600 * 1000).toISOString().replace('T', ' ').slice(0, 19);
  for (const e of entries) {
    try {
      await d1Run('INSERT INTO dead_log (pool,uid,name,reason,at) VALUES (?,?,?,?,?)',
        [POOL_NAME,
         e && e.uid != null && String(e.uid) !== '' ? String(e.uid) : null,
         e && e.name ? String(e.name) : null,
         reason || 'unknown', at]);
    } catch (err) { console.error('D1 死号流水写入失败:', err && err.message); }
  }
}

// 北京时间时间戳（YYYY-MM-DD HH:MM:SS），dead_log / dead_notice 统一口径，字符串可比大小
function bjStamp(ms) {
  return new Date((ms != null ? ms : Date.now()) + 8 * 3600 * 1000).toISOString().replace('T', ' ').slice(0, 19);
}

// 手动删号的「是否通知号主」队列（2026-10-26 新增，与主群 cron-relay 同一张 D1 表）。
// 定制群这边同样的问题：/admin 后台删号是在 worker 内部直接删 D1 行完成的，
// 没有 Python 进程参与，而 smtp.qq.com:465 只能从 Actions 发 → 号主收不到任何通知。
// 写法与 cron-relay 完全一致：删除即入队(pending)，判定和发信都在主群 worker 上做
// （/api/dead_pending 查 accounts 时不限 pool，所以 dz 的记录同样能判「有没有回来」）。
async function d1QueueNotice(e) {
  if (!d1ok() || !e) return false;
  return d1Run('INSERT OR IGNORE INTO dead_notice (pool,uid,name,email,removed_at,state) VALUES (?,?,?,?,?,?)',
    [POOL_NAME, String(e.uid != null ? e.uid : ''), String(e.name || ''), String(e.email || '').trim(), bjStamp(), 'pending']);
}

// 号主邮件队列 mail_queue（2026-11-06，与主群同一张 D1 表）：登记成功邮件入队用。
// 判定/派发都在主群 worker（/api/mail_pending、/api/mail_sent）+ 主群 Actions（notify_mail.py），
// 这边只需要在登记成功后排一条 pending。任何失败只记日志，绝不影响登记。
async function mailEnqueue(pool, uid, kind, ref, email, name, agent, exp) {
  if (!d1ok()) return false;
  return d1Run('INSERT OR IGNORE INTO mail_queue (pool,uid,kind,ref,email,name,agent,exp,state,created_at) ' +
    'VALUES (?,?,?,?,?,?,?,?,?,?)',
    [String(pool || ''), String(uid != null ? uid : ''), String(kind || ''), String(ref || ''),
     String(email || '').trim(), String(name || ''), String(agent || ''), String(exp || ''),
     'pending', bjStamp()]);
}

async function d1Run(sql, params) {
  if (!d1ok()) return false;
  try {
    const st = DB.prepare(sql);
    if (params && params.length) await st.bind(...params).run(); else await st.run();
    return true;
  } catch (e) { console.error('D1 run 失败:', e && e.message); return false; }
}
// 2026-11-09 新增（与主群同名同义）：返回实际改动行数。
// 返回 -1 = D1 不可用 / 执行失败（调用方必须当失败，绝不能当 0 行）。
// 存在的原因只有一个：d1Delete 要区分「真删了」和「WHERE 一行没匹配上」。
async function d1Changes(sql, params) {
  if (!d1ok()) return -1;
  try {
    const st = DB.prepare(sql);
    const r = (params && params.length) ? await st.bind(...params).run() : await st.run();
    return (r && r.meta && typeof r.meta.changes === 'number') ? r.meta.changes : 0;
  } catch (e) { console.error('D1 changes 失败:', e && e.message); return -1; }
}
// 单条镜像（新增/修改后调用）；无 uid 的历史条目跳过（无法按 uid 定位）
async function d1Upsert(e) {
  if (!d1ok() || !e) return false;
  const uid = e.uid != null ? String(e.uid) : '';
  if (!uid) return false;
  return d1Run(
    'INSERT INTO accounts (pool,uid,name,song,ck,added,exp,no_listen,email,updated_at,agent,plan,pub) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ' +
    'ON CONFLICT(pool,uid) DO UPDATE SET name=excluded.name, song=excluded.song, ck=excluded.ck, ' +
    'added=excluded.added, exp=excluded.exp, no_listen=excluded.no_listen, email=excluded.email, ' +
    'updated_at=excluded.updated_at, pub=excluded.pub, ' +
    // 2026-10-27：agent/plan 只在「新值非空」时覆盖，避免从 KV 老数据回灌时把客服归属清空
    'agent=CASE WHEN excluded.agent<>\'\' THEN excluded.agent ELSE accounts.agent END, ' +
    'plan=CASE WHEN excluded.plan<>\'\' THEN excluded.plan ELSE accounts.plan END, ' +
    // 2026-11-04：号主重新登记（CK 真变了）→ 清掉「已通知重登」，下一轮自动回到听众环。
    'relogin_at=CASE WHEN accounts.ck<>excluded.ck THEN \'\' ELSE COALESCE(accounts.relogin_at,\'\') END',
    [POOL_NAME, uid, String(e.name || ''), String(e.song || ''), String(e.ck || ''), String(e.added || ''),
     String(e.exp || ''), e.noListen ? 1 : 0, String(e.email || ''), new Date().toISOString(),
     String(e.agent || ''), String(e.plan || ''), e.pub ? 1 : 0]
  );
}
// ====================================================================
// 成交台账 ledger（2026-11-05，与 cron-relay 同一张表、同一个 D1 库）
// 背景：客服按「登记单数」单独拿提成，但掉线的客户要免费补一个号（补号不给提成）；
//       结算是次月 15 号回头算上月，所以必须有一份【不会随删号/改套餐漂移】的成交台账。
//       accounts 是「当前状态」——删号整行消失、改套餐原地覆盖，拿它算历史月账会凭空少单。
// 语义：
//   day      成交日（= 登记日 added 的日期部分），结算按这个月分组
//   start    服务开始日（补号时继承原单的 start）
//   exp      到期日（补号时继承原单的 exp，不重置）
//   price    单价（元）；NULL = 该档位没定价 → 结算页单列「待补价」，绝不当 0 元混进合计
//   rb       1 = 补号（免费补偿）：不计营收、不计提成，明细里单独一块
//   rb_from  关联的原单 ledger.id
//   src      reg=登记时自动记 / backfill=历史回填 / manual=人工补录
// 唯一键 (pool,uid,day)：同一个号同一天只留一笔，重复登记走更新不新增。
// 本仓只在登记时写（src=reg）；补号标记 / 人工补录 / 月度结算都在 cron-relay 控制台做。
// ====================================================================
function ledgerUidOf(e) {
  const u = (e && e.uid != null && String(e.uid) !== '') ? String(e.uid) : ('name:' + String((e && e.name) || ''));
  return (u === 'name:' || !u) ? '' : u;
}
// 写一笔成交流水。任何异常都吞掉（记账失败绝不能让登记失败）。
async function ledgerAdd(e, opt) {
  if (!d1ok() || !e) return false;
  const o = opt || {};
  const uid = ledgerUidOf(e);
  if (!uid) return false;
  let price = -1;
  let days = 0;
  try {
    const rc = await regCfg();
    price = planPrice(rc, e.plan);
    const pl = (rc.plans || []).find(it => it.key === e.plan || it.label === e.plan);
    days = pl ? (Number(pl.days) || 0) : 0;
  } catch (_e) { price = -1; }
  const added = String(e.added || '') || beijingDateTime();
  const day = added.slice(0, 10) || beijingDate();
  const exp = String(e.exp || '') || 'forever';
  // 已标记补号的那笔不能被「重新登记/回灌」洗回正常单 —— 否则免费补号下个月又被算一次提成
  return d1Run(
    'INSERT INTO ledger (pool,uid,name,agent,plan,price,days,day,start,exp,rb,rb_from,remark,src,at) ' +
    'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ' +
    'ON CONFLICT(pool,uid,day) DO UPDATE SET name=excluded.name, agent=excluded.agent, ' +
    'plan=excluded.plan, price=excluded.price, exp=excluded.exp, at=excluded.at, ' +
    'rb=CASE WHEN ledger.rb=1 THEN 1 ELSE excluded.rb END, ' +
    'rb_from=CASE WHEN ledger.rb=1 THEN ledger.rb_from ELSE excluded.rb_from END, ' +
    'remark=CASE WHEN excluded.remark<>\'\' THEN excluded.remark ELSE ledger.remark END',
    [POOL_NAME, uid, String(e.name || ''), String(e.agent || ''), String(e.plan || ''),
     price >= 0 ? price : null, days, day, String(o.start || day), exp,
     o.rb ? 1 : 0, Number(o.rbFrom) || 0, String(o.remark || ''), String(o.src || 'reg'),
     beijingDateTime()]
  );
}

// 2026-11-09 修复「D1 没删掉、KV 侧当删成功」（与 hz 同步）：
// 旧实现走 d1Run，只要 SQL 不抛异常就 return true —— 命中 0 行同样回 true，
// 上层照删 KV 键 + 写墓碑，号还在 D1 天天跑、KV 里却永久消失。
// 现在按 meta.changes 判：>0 才算删成功；=0 时再查一次把「本来就不存在」和「条件没匹配」分开。
async function d1Delete(e) {
  if (!d1ok() || !e) return false;
  const uid = e.uid != null ? String(e.uid) : '';
  let del, chk, params;
  if (uid) {
    del = 'DELETE FROM accounts WHERE pool=? AND uid=?';
    chk = 'SELECT 1 AS x FROM accounts WHERE pool=? AND uid=?';
    params = [POOL_NAME, uid];
  } else if (e.name) {
    del = 'DELETE FROM accounts WHERE pool=? AND name=?';
    chk = 'SELECT 1 AS x FROM accounts WHERE pool=? AND name=?';
    params = [POOL_NAME, String(e.name)];
  } else {
    return false;
  }
  const n = await d1Changes(del, params);
  if (n < 0) return false;          // D1 不可用/执行失败 → 判失败
  if (n > 0) return true;           // 真删掉了
  const left = await d1All(chk, params);
  if (left === null) return false;  // 读失败 → 判失败，宁可留着 KV 也不误删
  return left.length === 0;
}

const D1_COLS = 'uid,name,song,ck,added,exp,no_listen,email,agent,plan,pub';

// ---- 2026-11-08 省额度：全池读的排序从 SQL 挪到 JS（与 hz 同一套，详见 hz/worker.js 注释）----
// D1 把 `USE TEMP B-TREE FOR ORDER BY` 也算进 rows_read，带 ORDER BY 是 2 倍读行数。
// 排序结果已用真实数据逐行比对：与 `ORDER BY added, uid` 完全相同（全是 ASCII，BINARY 排序等价）。
function d1PoolCmp(a, b) {
  const x = String(a && a.added != null ? a.added : '');
  const y = String(b && b.added != null ? b.added : '');
  if (x !== y) return x < y ? -1 : 1;
  const u = String(a && a.uid != null ? a.uid : '');
  const v = String(b && b.uid != null ? b.uid : '');
  return u < v ? -1 : (u > v ? 1 : 0);
}

// ---- 2026-11-08 省额度：登记查重不再用 OR（与 hz 同一套）----
// `pool=? AND (uid=? OR name=?)` 的 OR 让索引失效 → 全池扫；拆成两条单条件查询各走索引。
// 返回：命中行数组；任一查询失败返回 null（= 查不了，交给上层回退 KV，绝不当作"没查到"）。
async function d1FindDup(uidKey, name) {
  const nm = String(name || '');
  const qs = [];
  if (uidKey) qs.push(d1All('SELECT uid,exp FROM accounts WHERE pool=? AND uid=? LIMIT 1', [POOL_NAME, uidKey]));
  if (nm) qs.push(d1All('SELECT uid,exp FROM accounts WHERE pool=? AND name=? LIMIT 1', [POOL_NAME, nm]));
  if (!qs.length) return [];
  const rs = await Promise.all(qs);
  const out = [];
  for (const r of rs) {
    if (r === null) return null;
    for (const x of r) out.push(x);
  }
  return out;
}

// D1 行 → KV entry 结构（保持字段名完全一致，上层代码无需改动）
// ====================================================================
// 2026-11-09：删号前复核整段删除了（原来有两版）——
//   ① neteaseUserAlive（2026-11-03）：用别的活号查 /api/v1/user/detail/<uid>，
//      code=200 就认为「账号还在，不能删」。它证明不了「这个 CK 还能用」，
//      于是「CK 死了、账号还在」（换设备/被顶号，最常见）被无限保留（11-09 清 6 个挂 5 天）。
//   ② ckAlive（2026-11-09 当日试验）：用号自己的 CK 调明文 /api/nuser/account/get。
//      实测不可用 —— 对池内随机 6 个健康号全部回 {code:200,account:null}，
//      而当天 dead_log 只删了 8 个 ⇒ 该判据在没有播放环境的出口 IP 上没有区分度。
// 结论：确认动作交给客户端（run.py.login_by_cookie：weapi account/get + v1 每日推荐双证据，
//   3 次里 2 次明确失效才判死），服务端收到 confirm=true 直接删 + 立刻直邮发信。
// 不要在这里重新引入任何「服务端再验一次 CK」的逻辑 —— 已验证不可靠。

function d1RowToEntry(r) {
  const uidRaw = String(r.uid || '');
  // 无 uid 的历史条目在库里用 'name:xxx' 占位（导入时补的），这里还原成「无 uid」
  const e = {
    name: String(r.name || ''),
    song: String(r.song || ''),
    ck: String(r.ck || ''),
    added: String(r.added || ''),
    exp: String(r.exp || ''),
    email: String(r.email || ''),
    // 2026-10-27：客服标签 + 套餐档位（与主群同一套口径；存量统一「徐」/空=未标注）
    agent: String(r.agent || ''),
    plan: String(r.plan || ''),
  };
  if (uidRaw && !uidRaw.startsWith('name:')) e.uid = r.uid;
  if (r.no_listen) e.noListen = 1;
  // 2026-11-01：公益号（只帮别人听、自己的歌不进互听环、不签到）
  if (r.pub) e.pub = 1;
  return e;
}

// 返回 null = D1 不可用/查询失败/表为空（调用方回退 KV）；返回数组 = 正常
async function d1Pool() {
  if (!d1ok()) return null;
  // 2026-11-08：ORDER BY 去掉（改 JS 排，见 d1PoolCmp），每次全池读省一半读行数。
  const rows = await d1All('SELECT ' + D1_COLS + ' FROM accounts WHERE pool=?', [POOL_NAME]);
  if (!rows) return null;
  if (!rows.length) {
    // 空表几乎不可能（账号池最少几十个号），当作异常处理，避免把「库被清空」误当成「账号池为空」
    console.error('D1 号池为空，回退 KV 读取');
    return null;
  }
  rows.sort(d1PoolCmp);
  return rows.map(d1RowToEntry);
}

// 计数型限流（2026-10-22 第三批）：D1 原子自增，返回自增后的计数。
// 为什么不用 KV：KV 是「读一次、加一、写回」，两个并发请求会读到同一个旧值 → 各写回 n+1，
// 等于少算一次，频控直接被绕过；而且 KV 免费额度写只有 1000 次/天。
// 语义：先自增再判断，超限的请求也计一次（宁可多算，不漏）。
// 返回 null = D1 不可用／写入失败，调用方必须回退 KV，不能让频控失效。
async function d1Hit(kind, key) {
  if (!d1ok()) return null;
  const k2 = kind + ':' + key;
  const ok = await d1Run(
    'INSERT INTO rate_limit (k,n,at) VALUES (?,1,?) ON CONFLICT(k) DO UPDATE SET n=n+1, at=excluded.at',
    [k2, new Date().toISOString()]);
  if (!ok) return null;
  const rows = await d1All('SELECT n FROM rate_limit WHERE k=?', [k2]);
  if (!rows || !rows.length) return null;
  return Number(rows[0].n) || 0;
}

// ---- 单键账号池快照（2026-10-22 第三批）----
// 背景：mergePoolKV 原来是「list 一次 + 每个 entry 键 get 一次」。账号池涨到 1000+ 时就是
// 1001+ 次外部操作，而单个 invocation 最多只能做 1000 次外部操作（Cloudflare 硬限）→
// D1 一挂，KV 兜底路径自己也必然失败，等于「灾备是假的」。
// 做法：维护一个 pool:<池> 单键（全池 JSON），兜底时 1 次读就拿到全池。
// 它不承担权威职责（entry: 键才是），只是为了「D1 不可用时这一轮还能跑起来」，偶尔落后无妨。
const poolSnapKey = () => 'pool:' + POOL_NAME;

async function refreshPoolSnap() {
  if (!d1ok()) return false;
  // 2026-11-08：同样去掉 ORDER BY（改 JS 排），省一半读行数；快照内容顺序不变。
  const rows = await d1All('SELECT ' + D1_COLS + ' FROM accounts WHERE pool=?', [POOL_NAME]);
  if (!rows || !rows.length) return false;
  rows.sort(d1PoolCmp);
  try {
    await POOL.put(poolSnapKey(), JSON.stringify(rows.map(d1RowToEntry)));
    return true;
  } catch (e) { console.error('号池快照写入失败:', e && e.message); return false; }
}

// ---- 每日轮转分配 ----
function dayIndexBJ() {
  const t = new Date(Date.now() + 8 * 3600 * 1000);
  return Math.floor(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate()) / 86400000);
}
function hashStr(s) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}
// ---- 网页访问口令（2026-10-25，与互助版 worker 同一套实现）----
// 需求：只拦【首页登记页】（GET / 与 /index.html）。口令存 KV 的 PAGE_PASS 键，值为空 = 不启用。
// 只拦网页，/api/* 一律放行 —— APK/EXE 直接调接口，加口令会让软件全线失效。
// cookie 里存的是 hashStr('pg:'+口令)，不落明文；带 ?k=口令 进来即种 cookie 并跳回原页面。
// 2026-10-26：只拦首页登记页。`/admin` 有自己的 KV ADMIN_PASS，再套一道 music88888
//   只会让人输两遍，而且 PAGE_PASS 是发给全体成员的，拿它当后台的第二道锁等于没锁。
//   （/g2 二群页已于同日整体下线，见 handle() 里的说明）
const GATE_COOKIE = 'pgate';
const PAGE_ROUTES = new Set(['/', '/index.html']);
function gateCookieValue(pass) { return String(hashStr('pg:' + pass)); }
async function pageGate(request, url) {
  let pass = '';
  try { pass = cleanKV(await POOL.get('PAGE_PASS')); } catch (e) {}
  if (!pass) return null;                                  // 未配置口令 → 直接放行
  const want = gateCookieValue(pass);
  if (url.searchParams.get('k') === pass) {                 // 带对口令 → 种 cookie，去掉 query 后回原页面
    return new Response(null, { status: 302, headers: {
      'Location': url.pathname || '/',
      'Set-Cookie': `${GATE_COOKIE}=${want}; Max-Age=31536000; Path=/; HttpOnly; SameSite=Lax`,
    } });
  }
  const ck = request.headers.get('Cookie') || '';
  const m = ck.match(new RegExp('(?:^|;\\s*)' + GATE_COOKIE + '=([^;]+)'));
  if (m && m[1] === want) return null;                      // cookie 已通过 → 放行
  return new Response(GATE_HTML, {
    status: 401,
    headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}
function seededShuffle(a, seed) {
  let s = (seed >>> 0) || 1;
  for (let i = a.length - 1; i > 0; i--) {
    s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0;
    const j = s % (i + 1); const t = a[i]; a[i] = a[j]; a[j] = t;
  }
  return a;
}
// 把「一行账号池数据」规整成计划用的结构：D1 行（snake）与 KV entry（camel）都能喂进来。
function planRow(r) {
  if (!r) return null;
  const noListen = r.no_listen ? 1 : (r.noListen ? 1 : 0);
  // 2026-11-01：公益号标记（pub=1）。只帮别人听，自己登记的歌不进互听歌环，也不参与签到。
  const pub = r.pub ? 1 : 0;
  // 是否有 CK：D1 主路径只回 0/1 的 hasck（省传输），KV 兜底路径行里直接有 ck。
  // 没有 CK 的行播不了，绝不能占听众名额 —— 否则那首歌每天白少一个听众，且谁也发现不了。
  const hasCk = (r.hasck !== undefined && r.hasck !== null)
    ? (Number(r.hasck) === 1)
    : (typeof r.ck === 'string' ? !!r.ck.trim() : true);
  return {
    pool: String(r.pool || POOL_NAME),
    uid: r.uid != null ? String(r.uid) : '',
    name: String(r.name || ''),
    song: String(r.song || ''),
    ck: String(r.ck || ''),
    email: String(r.email || ''),
    hasCk: hasCk,
    no_listen: noListen,
    relogin: r.relogin_at ? 1 : 0,
    pub: pub,
    added: String(r.added || ''),
    exp: String(r.exp || ''),
  };
}

// 纯计算（无 I/O）：D1 主路径与 KV 兜底共用同一套轮转逻辑，保证两条路算出的窗口完全一致。
// 2026-10-29：分片键 = uid 哈希桶（替掉原来的「列表下标 i % jobs」）。
// 背景（10-28 hz 覆盖率掉到 64.2% 的根因）：/api/assign 每次请求都重算 buildPlan，
// 再用 ownPool.filter((_, i) => i % jobs === job) 按「数组下标」分片。而一整夜跑的过程中
// 死号会被不断删除（实测全池 531 → 434），下标整体前移 ⇒ 同一个号被分到 2~3 片
//（实测 91 个号重复、白烧 113 个席位），另有 125 个计划号任何一片都没轮到。
// 改成按 uid 哈希取模后，每个号固定落在自己那一桶：池里增减只会影响它自己，
// 不会连锁漂移；代价是各片号数不再绝对均匀（约 ±40%，最重一片约为均值的 2 倍，仍在跑得完的范围）。
// 2026-11-04：分片键叠「日期盐」。原先纯 uid 哈希 => 同一批号天天被分到同一片，
// 也就是天天跑在同一台 VM 上：网易看到的不是「一个 IP 上有 6 个号」，而是
// 「这 6 个号永远同进同出，只是共用的 IP 每天在换」—— 真实用户不会这样，是结构性指纹。
// 盐取 plan.day（run.yml 的 ASSIGN_DAY / 定向补跑的 DAY_OVERRIDE），整轮任务内恒定，
// 所以「NS_OVERRIDE + ONLY_SLICES」补跑仍能精确复现失败那一轮的分片。
function sliceBucket(uid, jobs, salt) {
  const s = String(uid || '') + (salt ? '|' + salt : '');
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;      // FNV-1a 乘 16777619，Math.imul 保证 32 位不丢精度
  }
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b) >>> 0;   // murmur3 fmix32 收尾，避免低位分布不均
  h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35) >>> 0;
  h ^= h >>> 16;
  return (h >>> 0) % Math.max(1, jobs);
}

/* ============================================================================
   首周加速分配（2026-11-08，与 hz 主群同步）
   ----------------------------------------------------------------------------
   口径前提：650 = 近 30 日累计有效播放，平台去重口径是「同听众 + 同歌 + 同一天」。
   所以一首歌今天能涨多少，只取决于今天有多少个不同的号去听它；跨天重复仍计数。

   原来平均分配：每首歌每天刚好 M*p/L ≈ 32 个听众，650/32 要爬 21 天（首月 22 天）。

   改法：按「歌主入池天数」给每首歌定目标听众数：
     入池 1~7 天  : 118 人/天（= 108 理论值 + skip_prob 补偿，7 个自然日内冲满 100%）
     入池 8~21 天 : 32 人/天（与现状一致，在途客户零感知）
     入池 22 天+  : 25 人/天（早就满了；维持 100% 的下限是 22）
   每人每晚听几首 per ≈ 总槽位/听众数，会从 32 涨到 52 左右。
   30 从来是下限不是上限，只是新号的歌要多被 76 个人听，人得从别人身上匀出来。

   算法：每首歌一个「听众窗口」，起点在归一化号空间按天推进（详见 hz 版注释，
   含三条会让加速静默失效的坑：uid 稳定排序 / 归一化起点 / BASE_M）。

   ⚠ 两个群共用一份 D1、共用同一个歌环，本 worker 算出的 plan 必须与 hz 完全一致，
     否则跨群互听会错位。所以这段代码、常量、哈希算法都要跟 hz 保持一字不差。
   ============================================================================ */
const ACCEL_ON = true;          // 总开关：改 false 立刻回到原来的平均分配（应急回滚用）
const ACCEL_DAYS = 7;           // 入池 1~N 天算「加速档」
// 2026-11-09：108 → 118。108 是「650/6」的纯理论值，但 run.py 的 skip_prob（默认 0.08）会
// 随机跳过约 8% 的曲目（模拟真实切歌），那部分不计有效播放。按 108 算实际只有 ~99/天，
// 7 天 693 在「人-天次数」口径下刚刚够、在「不同听众」口径下只有 618 不够。
// 118 是 108 / 0.92 上取整，7 天 826 → 有效 ~760，两种口径都留得住余量。
const ACCEL_PER_DAY = 118;      // 加速档：每首歌每天要多少个不同听众（已含 skip_prob 补偿）
const KEEP_PER_DAY = 32;        // 在途档：与现状一致，不动存量客户的速度
const IDLE_PER_DAY = 25;        // 满档：已 100%，维持住的下限是 22
function daysBetween(from, to) {                 // to - from，单位天；非法值按「很远」处理
  const t1 = Date.parse(String(from || '').slice(0, 10) + 'T00:00:00Z');
  const t2 = Date.parse(String(to || '').slice(0, 10) + 'T00:00:00Z');
  if (!isFinite(t1) || !isFinite(t2)) return 999;
  return Math.floor((t2 - t1) / 86400000);
}
function accelTargetOf(added, today) {
  const d = daysBetween(added, today);
  if (d <= 0) return 0;
  if (d <= ACCEL_DAYS) return ACCEL_PER_DAY;
  if (d <= 21) return KEEP_PER_DAY;
  return IDLE_PER_DAY;
}
function buildPlanAccel(live, songs, listeners, today, idle) {
  const M = listeners.length, L = songs.length;
  if (!M || !L) return { ok: false, msg: '可用号或歌曲为空', m: M, l: L, idle, plans: [] };
  // 每首歌的目标按「登记它的号里入池最早的那个」算，与 hz 一致。
  const owner = {};
  for (const r of live) {
    if (r.pub) continue;
    if (r.relogin) continue;                     // 失效号的歌不进歌环，与 songs 的过滤保持一致
    const s = String(r.song || ''); if (!s) continue;
    const a = String(r.added || '');
    if (!owner[s] || (a && a < owner[s])) owner[s] = a;
  }
  const tgt = songs.map(s => accelTargetOf(owner[s], today));
  let S = 0;
  for (const t of tgt) S += t;
  if (!S) return { ok: false, msg: '目标听众全为 0', m: M, l: L, idle, plans: [] };
  // 单班时长保险，超限等比缩放（与 hz 一致，改一边必须同步另一边）。
  // 2026-11-09 二次修正：改成按「门闩 ÷ 波数」推导（与 hz 逐字相同），写死的 62/90 会随
  //   池子与分片漂移 —— M=682 时只剩 8% 余量、M=1200 时又该收到 60 却仍按 62 放行。
  //   APS 统一取 12（hz 的 run.yml 现值），不是本仓的 6：M 是全池号数、两仓必须算出同一份
  //   plan，按较小的 APS 算出来的波数只多不少，对 dz 只是保守，不会误稀释。
  // ⚠ 改 hz 的 ACCOUNTS_PER_SLICE / ACCOUNT_PARALLEL 必须同步改这 4 个常量（两边必须一致）。
  const APS_ASSUME = 12, JOB_CONC = 20, KNIFE_MIN = 520, MIN_PER_SONG = 1.52;
  const waves = Math.max(1, Math.ceil(Math.ceil(M / APS_ASSUME) / JOB_CONC));
  const PER_CAP = Math.max(16, Math.floor(KNIFE_MIN / waves / MIN_PER_SONG) - 8);
  let capped = 0;
  if (S / M > PER_CAP) {
    capped = 1;
    const ratio = PER_CAP * M / S;
    for (let j = 0; j < L; j++) tgt[j] = Math.max(1, Math.round(tgt[j] * ratio));
    S = 0;
    for (const t of tgt) S += t;
  }
  // 分配模型：每首歌一个听众窗口，起点在归一化号空间按天推进。三条硬约束见 hz 同名函数注释：
  // ① 号必须按 uid 稳定排序；② 起点不能用 `(h+day*t)%M`（池子每天变大会整体错位，实测掉 30%）；
  // ③ BASE_M <= 典型 M。两仓必须一模一样，否则跨群歌环错位。
  const BASE_M = 650;
  const day = Math.floor(Date.parse(today + 'T00:00:00Z') / 86400000);
  const order = new Array(M);
  for (let i = 0; i < M; i++) order[i] = i;
  order.sort((a, b) => (listeners[a].uid < listeners[b].uid ? -1 : listeners[a].uid > listeners[b].uid ? 1 : 0));
  const buckets = new Array(M);
  for (let j = 0; j < L; j++) {
    const t = tgt[j];
    if (!t) continue;
    let pos = (hashStr(songs[j]) / 4294967296 + day * t / BASE_M) % 1;
    if (pos < 0) pos += 1;
    const start = Math.floor(pos * M) % M;
    // 2026-11-09：t 可能 > M（D1 挂掉走 KV 兜底、池子里只剩几十个号时），原来 (start+k)%M
    // 会把同一首歌塞给同一个号两次 —— 同一天同号重复听完全不计播放，白烧一整首的时长。
    const times = Math.min(t, M);
    for (let k = 0; k < times; k++) {
      const i = (start + k) % M;
      const b = buckets[i];
      if (b) b.push(j); else buckets[i] = [j];
    }
  }
  const plans = [];
  // 配平：桶大小天然不均（p99 约 per 的 1.3 倍），而整轮时长由最慢的号决定。
  // 把超出 cap 的歌匀给不足 per 的号，每首歌听众总数不变。与 hz 一致。
  const per = Math.max(1, Math.round(S / M));
  const cap = per + 8;
  const over = [], thin = [];
  for (let i = 0; i < M; i++) {
    const b = buckets[i] || (buckets[i] = []);
    if (b.length > cap) {
      for (let x = cap; x < b.length; x++) over.push([b[x], i]);
      b.length = cap;
    }
    if (b.length < per) thin.push(i);
  }
  let ti = 0, nDone = 0;
  for (let n = 0; n < over.length && thin.length; n++) {
    nDone = n + 1;
    const j = over[n][0], src = over[n][1];
    let placed = false;
    for (let k = 0; k < thin.length; k++) {
      const i = thin[(ti + k) % thin.length];
      const b = buckets[i];
      // 2026-11-09：必须同时排除「这首歌主人自己的桶」。原来只查 indexOf(j)，没查 own：
      // 匀给歌主本人时，出 plan 阶段 s !== own 会把它剔掉 ⇒ 这首歌白少一个听众。
      // 实测「目标 108 人/天」那批 min=107（应是 108）就是这么来的。
      if (b.length >= per || b.indexOf(j) >= 0) continue;
      if (listeners[order[i]].song === songs[j]) continue;
      b.push(j); placed = true;
      ti = (ti + k + 1) % thin.length;
      break;
    }
    if (!placed) buckets[src].push(j);   // 找不到空位就留在原桶，不能让这首歌少一个听众
  }
  // 2026-11-09：上面循环条件带 thin.length，若初始所有桶都 >= per 就一次都不执行，
  // 已被 cap 截断进 over 的歌就凭空消失（那首歌少听众）。概率极低，撞上就是掉播放，
  // 补一趟：没处理到的 over 项放回原桶（宁可该号多听一首，也不能让歌少一个听众）。
  for (let n = nDone; n < over.length; n++) {
    const j = over[n][0], src = over[n][1];
    if (buckets[src].indexOf(j) < 0) buckets[src].push(j);
  }
  let maxPlays = 0, sumPlays = 0;
  for (let oi = 0; oi < M; oi++) {
    const it = listeners[order[oi]];
    const own = it.song;
    const bj = buckets[oi];
    const picks = [];
    if (bj) for (let x = 0; x < bj.length; x++) {
      const s = songs[bj[x]];
      if (s !== own) picks.push(s);
    }
    seededShuffle(picks, hashStr(it.uid + ':' + day));
    if (picks.length > maxPlays) maxPlays = picks.length;
    sumPlays += picks.length;
    plans.push({ pool: it.pool, uid: it.uid, name: it.name, song: own,
                 ck: it.ck, email: it.email, pub: it.pub ? 1 : 0, plays: picks });
  }
  const perAvg = Math.round(sumPlays / M);
  return { ok: true, day: today, m: M, l: L, p: perAvg, plans, idle,
           accel: { on: 1, days: ACCEL_DAYS, perDay: ACCEL_PER_DAY, slots: S, per: perAvg,
                    max: maxPlays, capped: capped } };
}

function buildPlanFrom(rows, today) {
  const live = rows.filter(r => {
    const added = String(r.added || '');
    if (added && added >= today) return false;               // 当天新登记的次日才跑
    const exp = String(r.exp || '');
    if (exp && exp !== 'forever' && exp < today) return false;
    return true;
  });
  // 2026-11-01：公益号登记的歌不进互听歌环（"自己的歌不需要别人听"），账号本身照常帮别人听。
  // 2026-11-08：CK 失效号（relogin 非空）同理 —— 原来只摘人不摘歌，等于让它们白占播放次数。
  // 号主重新登记清空 relogin_at 后歌会自动回来。（与 hz 保持一致，两仓必须同步改）
  const songs = [...new Set(live.filter(r => !r.pub && !r.relogin).map(r => String(r.song || '')).filter(Boolean))].sort();
  const seen = new Set();
  const listeners = [];
  const idle = [];                                           // 只收不听：不进播放环，但要下发去签到/查工作台/验活
  for (const r of live) {
    const uid = String(r.uid || '');
    const key = String(r.pool) + ':' + uid;
    if (!uid || seen.has(key)) continue;
    if (!r.hasCk) continue;                                  // 空 CK 占位行不占听众名额
    seen.add(key);
    const item = { pool: String(r.pool), uid, name: r.name || '', song: r.song || '',
                   ck: r.ck, email: r.email || '', pub: r.pub ? 1 : 0 };
    if (r.no_listen) { idle.push(item); continue; }
    // 2026-11-04：CK 已确认失效、账号仍在（判死加固 B 保留的那批）→ 摘出听众环，
    // 否则它只占「应跑」名额、每天验活失败，coverage 天天缺又看不出原因。
    if (r.relogin) { idle.push(item); continue; }
    listeners.push(item);
  }
  const M = listeners.length, L = songs.length;
  if (!M || !L) return { ok: false, msg: '可用号或歌曲为空', m: M, l: L, idle, plans: [] };
  // 2026-11-08：首周加速走「每首歌独立听众窗口」（与 hz 同步）。ACCEL_ON=false 回滚到下面的平均分配。
  if (ACCEL_ON) return buildPlanAccel(live, songs, listeners, today, idle);
  // p：先按「每首歌每天 ASSIGN_TARGET+1 个听众」反推，再夹进 [1, L-1]。
  // 2026-10-22 修正：原写法 Math.max(8, Math.min(L-1, x)) 在 L<9 时 p>L-1，每人取不满 p 首。
  const p = Math.max(1, Math.min(Math.max(8, Math.ceil((ASSIGN_TARGET + 1) * L / M)), Math.max(1, L - 1)));
  const day = Math.floor(Date.parse(today + 'T00:00:00Z') / 86400000);
  const off = ((day * p) % L + L) % L;
  const plans = [];
  for (let i = 0; i < M; i++) {
    const it = listeners[i];
    const base = Math.floor(i * L / M);
    const own = it.song;
    const picks = [];
    for (let j = 0; picks.length < p && j < L; j++) {
      const sid = songs[(base + off + j) % L];
      if (sid === own) continue;                             // 绝不听自己
      picks.push(sid);
    }
    seededShuffle(picks, hashStr(it.uid + ':' + day));
    plans.push({ pool: it.pool, uid: it.uid, name: it.name, song: own,
                 ck: it.ck, email: it.email, plays: picks });
  }
  return { ok: true, day: today, m: M, l: L, p, plans, idle };
}

// 返回全量 listeners 的播放计划；调用方按 i % jobs 取自己那一批。
// 覆盖性证明：第 i 个号的窗口起点 base=floor(i*L/M)，长度 p ⇒ 任一歌曲位置被
// 恰好 p*M/L（向上取整后 ≥p）个窗口覆盖 ⇒ 每首歌每天都有听众，且方差极小。
// 每日轮转：offset 每天 +p（=窗口长度）⇒ 相邻两天窗口完全不重叠 ⇒ 听众集合全换。
async function buildPlan(dayStr) {
  // dayStr：整轮任务统一的「日期锚点」（由 run.yml 的 plan job 下发）。
  // 不传则用北京时间今天。锚定它的原因：账号池大到一晚跑不完时会分成多波，
  // 若跨过午夜，各波会算出不同的轮转偏移 —— 那样有的歌被听两遍、有的没人听。
  const today = /^\d{4}-\d{2}-\d{2}$/.test(dayStr || '') ? dayStr : beijingDate();
  // 两群共用一个 D1：歌环与听众环都按「全池」计算，本 worker 只投递自己群的那批号。
  // 这样跨群继续有效（主群的号也会听到定制群的歌），且两边算出的计划完全一致。
  // 注意 SELECT 里那个 hasck：只回 0/1，用来判断「这条能不能播」，比把 ck 整列拉回来省 200 倍传输。
  const rows = await d1All("SELECT pool,uid,name,song,no_listen,pub,added,exp,relogin_at,"
    + "(CASE WHEN ck IS NULL OR TRIM(ck)='' THEN 0 ELSE 1 END) AS hasck "
    + "FROM accounts ORDER BY pool, uid");
  if (rows) return buildPlanFrom(rows.map(planRow), today);
  // 2026-10-22：D1 不可用时用 KV 逐号备份兜底（以前直接返回失败 → run.py 回退到冻结的
  // Secrets 分片，那一晚只有极少数号在跑，而且 job 还是绿的）。KV 里只有本群的号，
  // 跨群会退化成「只听本群」，但绝不会变成 0 个号。
  console.error('D1 查询失败，buildPlan 回退 KV 逐号备份');
  try {
    const kv = await mergePoolKV();
    if (kv && kv.length) {
      const plan = buildPlanFrom(kv.map(planRow), today);   // KV 行自带 ck，planRow 会判空
      plan.src = 'kv';
      return plan;
    }
  } catch (e) { console.error('buildPlan 的 KV 兜底也失败:', e && e.message); }
  return { ok: false, msg: 'D1 未绑定或查询失败，且 KV 兜底无数据' };
}

/* ============================================================================
   2026-11-09：当轮 plan 名单快照（D1 表 plan_snap）— 与主群 worker 逐字同构
   ----------------------------------------------------------------------------
   /api/coverage 的 expected 原来用「当下实时 buildPlan」算、ran 用「当天 runs 表」，
   两边不是同一时刻的集合：白天池子一动（删号/新登记/到期降公益）就会假报缺号或漏真缺号。
   改法：每轮 plan job 第一次调 /api/pool_stat 时把本池应跑名单落一行快照，
   之后全天补跑/coverage 都对齐它（首轮 winner，补跑不覆盖）。
   两群共用同一张 D1，所以 hz/dz 各占 (day,pool) 一行互不干扰。
   ============================================================================ */
async function planSnapGet(day, pool) {
  if (!d1ok()) return null;
  try {
    const rows = await d1All('SELECT uids,n,src,at FROM plan_snap WHERE day=? AND pool=?',
                             [String(day), String(pool)]);
    if (!rows || !rows.length) return null;          // null = 读失败，[] = 真没有
    let uids = [];
    try { uids = JSON.parse(rows[0].uids) || []; } catch (e) { return null; }
    if (!Array.isArray(uids) || !uids.length) return null;
    return { pool: String(pool), uids: uids.map(String), n: Number(rows[0].n) || uids.length,
             src: String(rows[0].src || ''), at: String(rows[0].at || '') };
  } catch (e) { return null; }
}

async function planSnapPut(day, pool, uids, src) {
  if (!d1ok() || !uids || !uids.length) return false;
  try {
    const ex = await d1All('SELECT day FROM plan_snap WHERE day=? AND pool=?',
                           [String(day), String(pool)]);
    if (ex === null || ex.length) return false;
    const arr = uids.map(String);
    return await d1Run('INSERT OR IGNORE INTO plan_snap (day,pool,uids,n,src,at) VALUES (?,?,?,?,?,?)',
      [String(day), String(pool), JSON.stringify(arr), arr.length, String(src || 'd1'), bjStamp()]);
  } catch (e) {
    console.error('plan_snap 写入失败（coverage 自动回退实时口径）:', e && e.message);
    return false;
  }
}

async function handle(request) {
    const url = new URL(request.url);
    // 2026-10-25：网页口令统一闸门（KV PAGE_PASS，未配置则不启用）。只拦网页，/api/* 一律放行 ——
    // APK/EXE 直接调接口，加口令会让软件全线失效。
    if (PAGE_ROUTES.has(url.pathname)) {
      const gate = await pageGate(request, url);
      if (gate) return gate;
    }
    if (url.pathname === '/' || url.pathname === '/index.html') {
      // 2026-10-22：页面「账号池上限 N 人」按 KV 实时渲染（定制版固定走 POOL_LIMIT_G2，默认 500）
      let lim = 500;
      try { lim = parseInt(cleanKV(await POOL.get('POOL_LIMIT_G2')), 10) || 500; } catch (e) {}
      return new Response(INDEX_HTML_DZ.replace('__POOL_LIMIT__', String(lim)),
        { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } });
    }
    // 2026-10-26：二群登记页 /g2 已整体下线（用户明确要求，该页面从未投入使用）。
    // 原来这里返回 INDEX_HTML_G2；对应模板、cfg 的 groupPass2 字段一并删除。
    // 现在只剩：首页登记页 /、管理后台 /admin。
    // ---- 群主管理后台（只读）：ADMIN_PASS 独立口令，NOT 群口令 ----
    if (url.pathname === '/admin' && request.method === 'GET') {
      return new Response(ADMIN_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } });
    }
    // ---- 客服名单 + 套餐档位（2026-10-27）：APK / EXE 登记前拉一次，改名单不用重发软件 ----
    // 与主群读同一份 D1 kv_misc.reg_cfg，所以两群名单永远一致。不含账号信息，故不鉴权。
    if (url.pathname === '/api/agents') {
      const CORS = { 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' };
      if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: {
        'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type' } });
      if (request.method !== 'GET') return json({ message: '请用 GET' }, 405, CORS);
      const rca = await regCfg();
      return json({ ok: true, agents: rca.agents, plans: rca.plans, at: new Date().toISOString() }, 200, CORS);
    }
    // 本地后台网页（账号池管理网页.html）跨域调用本接口：放开 CORS 并处理预检
    if (url.pathname === '/api/pool' && request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
      } });
    }
    if (url.pathname === '/api/pool' && request.method === 'POST') {
      const CORS = { 'Access-Control-Allow-Origin': '*' };
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400, CORS); }
      const c = await cfg();
      /* 2026-11-11 v2.12：号池【查看】口令放宽 —— ADMIN_PASS / CONSOLE_PASS / CONSOLE_RO_PASS
         任一可读（与主群同口径）。APK 号池页切到定制版输满权/只读码，之前必报「管理密码错误」，
         因为这里原先只认 ADMIN_PASS。纯读接口，写操作（/api/admin/entry 等）仍只认 ADMIN_PASS。 */
      const noPassAtAll = !c.adminPass && !c.consolePass && !c.consoleRoPass;
      if (noPassAtAll) return json({ message: '尚未设置管理密码：请在 Cloudflare KV 中添加 ADMIN_PASS 键（任意长随机字符串）' }, 503, CORS);
      const poolViewOk = !!body.pass && (body.pass === c.adminPass || body.pass === c.consolePass || body.pass === c.consoleRoPass);
      if (!poolViewOk) return json({ message: '管理密码错误' }, 403, CORS);
      /* 2026-11-09：原来每次刷新管理页都跑一遍 pruneExpired()（重建全池 + 写副作用），
         而「到期降级」已由主群每日 cron 负责。这里改成纯读。 */
      const master = await mergePool();
      // 只回展示字段，绝不下发 ck（cookie）等敏感数据
      const entries = master.map(e => ({
        name: e.name || '', uid: e.uid != null ? String(e.uid) : '',
        song: e.song != null ? String(e.song) : '', added: e.added || '',
        email: e.email || '', phone: e.phone || '', noListen: !!e.noListen, exp: e.exp || '',
        // 2026-10-27：主群控制台要按客服/套餐筛选，定制群的号也必须带上这两项
        agent: e.agent || '', plan: e.plan || '',
        // 2026-11-01：公益号标记
        pub: !!e.pub,
      }));
      const stats = {
        total: entries.length,
        withMail: entries.filter(e => e.email).length,
        noMail: entries.filter(e => !e.email).length,
        noListen: entries.filter(e => e.noListen).length,
        public: entries.filter(e => e.pub || !e.song).length,
        expiring: entries.filter(isSoonExpired).length,
        manual: entries.filter(e => String(e.name).indexOf('qr:') === 0 || String(e.name).indexOf('manual:') === 0).length,
        limit: c.poolLimitG2,
        remain: Math.max(0, c.poolLimitG2 - entries.length),
      };
      return json({ ok: true, stats: stats, entries: entries }, 200, CORS);
    }
    // ---- 跨群歌单（2026-10-20）：只回"可以被听到的歌曲 id"，绝不回任何账号/cookie 信息。
    //      定制群与协同群互相拉这份列表，把两边的歌并成一个歌池，但两个 KV 账号池独立、人数各算各的。
    //      口令 = KV 键 PEER_KEY（2026-10-26 起；未配置才回退旧的 PEER_PASS 对穿）；未设置则该接口不开放。
    if (url.pathname === '/api/songs' && request.method === 'GET') {
      const CORS = { 'Access-Control-Allow-Origin': '*' };
      // 2026-10-26 补丁：原来这里只认 PEER_PASS，而 run.py 已改用 PEER_KEY 调对端 →
      // 互助群拉定制群歌单会 403，跨群互听悄悄退化成「只听本群」。统一走 peerPassOk。
      if (!(await peerPassOk(url.searchParams.get('pass')))) {
        if (!(await peerKey()) && !cleanKV(await POOL.get('PEER_PASS')))
          return json({ message: '未开启跨群互听：请在 KV 添加 PEER_KEY 键' }, 503, CORS);
        return json({ message: '口令错误' }, 403, CORS);
      }
      // 2026-10-22：取歌单是只读高频接口，原来每次调用都跑 pruneExpired（全量重建 + 推 Secret）。
      // 改为单条 SELECT DISTINCT，过期号交给管理后台/resync 清理。
      let songs;
      const rows = d1ok()
        ? await d1All("SELECT DISTINCT song FROM accounts WHERE pool=? AND song<>'' AND pub=0 ORDER BY song", [POOL_NAME])
        : null;
      if (rows) songs = rows.map(r => String(r.song)).filter(Boolean);
      else songs = (await mergePool()).filter(e => !e.pub).map(e => String(e.song || '')).filter(Boolean);
      songs = [...new Set(songs)].sort();
      return json({ ok: true, count: songs.length, songs: songs }, 200, CORS);
    }
    // ---- D1 分配接口（2026-10-22 新增）：run.py 直接问「本班跑哪些号、每号听什么」----
    // 鉴权用群口令（run.py 本来就有 GROUP_PASS 环境变量）；口令为空时拒绝服务。
    if ((url.pathname === '/api/assign' || url.pathname === '/api/pool_stat') && request.method === 'GET') {
      const c = await cfg();
      const pass = url.searchParams.get('pass') || '';
      // 2026-10-22 安全修正：本接口会回明文 CK，绝不能再用「群口令」鉴权（定制版群口令同时是
      // 协同版的对穿口令，泄露面更大）。只认独立键 ASSIGN_PASS；ADMIN_PASS 仍放行便于手工排错。
      if (!c.assignPass) return json({ ok: false, message: '未配置分配口令（KV 键 ASSIGN_PASS），D1 分配接口未开放' }, 503);
      const okPass = pass === c.assignPass;
      const okAdmin = c.adminPass && pass === c.adminPass;
      if (!okPass && !okAdmin) return json({ ok: false, message: '口令错误' }, 403);
      if (!d1ok()) return json({ ok: false, message: 'D1 未绑定' }, 503);
      const t0 = Date.now();
      if (url.pathname === '/api/pool_stat') {
        const plan = await buildPlan(url.searchParams.get('day'));
        if (!plan.ok) return json({ ok: false, message: plan.msg }, 503);
        const own = plan.plans.filter(x => x.pool === POOL_NAME);
        const mine = own.length;
        const idleN = (plan.idle || []).filter(x => x.pool === POOL_NAME).length;
        // 2026-11-09：落「当轮应跑名单」快照，供 /api/coverage 按同一口径比对（首轮 winner）。
        let snapWrote = 0;
        try {
          snapWrote = (await planSnapPut(plan.day, POOL_NAME, own.map(x => String(x.uid)), plan.src || 'd1')) ? 1 : 0;
        } catch (e) {}
        return json({ ok: true, pool: POOL_NAME, day: plan.day, m: plan.m, l: plan.l,
                      p: plan.p, m_pool: mine, idle: idleN, src: plan.src || 'd1',
                      accel: plan.accel || null, snap: snapWrote, ms: Date.now() - t0 });
      }
      const job = Math.max(0, parseInt(url.searchParams.get('job') || '0', 10) || 0);
      const jobs = Math.max(1, parseInt(url.searchParams.get('jobs') || '1', 10) || 1);
      if (job >= jobs) return json({ ok: false, message: 'job 超出范围' }, 400);
      const plan = await buildPlan(url.searchParams.get('day'));
      if (!plan.ok) return json({ ok: false, message: plan.msg }, 503);
      const ownPool = plan.plans.filter(x => x.pool === POOL_NAME);
      // 2026-11-06：本群 0 个号、全池却有号 —— 要么本群池真空了，要么 pool 字段对不上。
      // 以前这里静默返回 0 个号，run.py 分不清「本群真没号」和「接口这次出错」。
      if (!ownPool.length && plan.m > 0) {
        console.error('[assign] 本群 0 个号，但全池有 ' + plan.m + ' 个（pool=' + POOL_NAME + ', src=' + (plan.src || 'd1') + '）');
      }
      // 2026-10-29：按 uid 哈希桶分片（sliceBucket），不再用数组下标，池变动不漂移。
      const mine = ownPool.filter(x => sliceBucket(x.uid, jobs, plan.day) === job);
      // 只收不听的号（no_listen）以前完全不进 assign → 不日常、不查工作台、不验活、死了也不报。
      // 现在按同一套 sliceBucket 分片下发，run.py 只让它们查工作台/上报，不参与播放。
      const ownIdle = (plan.idle || []).filter(x => x.pool === POOL_NAME);
      const mineIdle = ownIdle.filter(x => sliceBucket(x.uid, jobs, plan.day) === job);
      // D1 主路径为省传输没查 ck/email，这里按本片那几个号补一次；KV 兜底路径自带 ck，不会触发。
      const meta = {};
      const need = mine.concat(mineIdle).filter(x => !x.ck);
      // 2026-10-24 修复：D1 单条 SQL 最多 100 个绑定参数（实测 101 个即报
      // "too many SQL variables"）。本池目前 90 个号刚好没超，一旦涨过 100，
      // snapshot 用 jobs=1 拉全池时会整条查询失败 → 补不到 ck → 返回 0 个号。
      // 改为每批 90 个 uid 分次查；正常播放路径 jobs=250（每片 1-2 个号）行为不变。
      for (let i = 0; i < need.length; i += 90) {
        const uids = need.slice(i, i + 90).map(x => x.uid);
        const ph = uids.map(() => '?').join(',');
        const rs = await d1All('SELECT uid,name,ck,email FROM accounts WHERE pool=? AND uid IN (' + ph + ')',
                               [POOL_NAME].concat(uids));
        // 2026-11-06 关键修复：这次补查失败（D1 额度耗尽 / 网络中断）时 d1All 返回 null，
        // 原来的 `(rs || [])` 把它当成「这些号没有 CK」→ 下面 filter(x => x.ck) 会把整片号
        // 全部滤掉 → 接口返回 0 个号 → run.py 判定「没分到名单」→ 回退仓库里的 10 月老名单
        // ⇒ 11-06 那次「主群 127 号双播 / 137 号零播、定制群 16 号双播 / 23 号零播」的真实起点。
        if (!rs) return json({ ok: false, message: 'D1 查询失败（本片 CK 补查），请稍后重试' }, 503);
        for (const r of rs) meta[String(r.uid)] = r;
      }
      const pack = x => {
        const m = x.ck ? x : (meta[x.uid] || {});
        return { uid: x.uid, name: m.name || x.name || '', ck: m.ck || x.ck || '',
                 email: m.email || x.email || '', song: x.song || '', plays: x.plays || [],
                 // 2026-11-01：公益号标记（make_accounts.py 据此跳过签到/发笔记）
                 pub: x.pub ? 1 : 0 };
      };
      const accounts = mine.map(pack).filter(x => x.ck);
      const idle = mineIdle.map(pack).filter(x => x.ck);
      return json({ ok: true, pool: POOL_NAME, day: plan.day, m: plan.m, l: plan.l, p: plan.p,
                    m_pool: ownPool.length, jobs: jobs, job: job, src: plan.src || 'd1',
                    accounts: accounts, idle: idle, ms: Date.now() - t0 });
    }
    // ---- 覆盖率核对（与主群同构，2026-10-22 同步）：应跑 vs 实跑 ----
    // 默认查本池（dz）；带 ?pool=hz 也能查另一池 —— 两群共用一个 D1，runs 表按 pool 分开。
    if (url.pathname === '/api/coverage' && request.method === 'GET') {
      const c = await cfg();
      const pass = url.searchParams.get('pass') || '';
      if (!c.assignPass) return json({ ok: false, message: '未配置 ASSIGN_PASS' }, 503);
      if (pass !== c.assignPass && !(c.adminPass && pass === c.adminPass)) return json({ ok: false, message: '口令错误' }, 403);
      if (!d1ok()) return json({ ok: false, message: 'D1 未绑定' }, 503);
      const day = /^\d{4}-\d{2}-\d{2}$/.test(url.searchParams.get('day') || '')
        ? url.searchParams.get('day') : beijingDate();
      const poolQ = url.searchParams.get('pool') || POOL_NAME;
      // 2026-11-09：expected 优先取「当轮 plan 快照」；没有快照（老日期 / D1 读不到）才回退实时 buildPlan。
      let expected = null, expSrc = '', snapAt = '';
      const snap = await planSnapGet(day, poolQ);
      if (snap) {
        expected = snap.uids; expSrc = 'snap'; snapAt = snap.at;
      } else {
        const plan = await buildPlan(day);
        if (!plan.ok) return json({ ok: false, message: plan.msg }, 503);
        expected = plan.plans.filter(x => x.pool === poolQ).map(x => String(x.uid));
        expSrc = 'live';
      }
      const rows = await d1All('SELECT uid FROM runs WHERE day=? AND pool=?', [day, poolQ]);
      // 2026-11-06：读失败不能当成「一个都没跑」——会发出「覆盖率 0%」的假告警。
      if (!rows) return json({ ok: false, message: 'D1 查询失败（runs 表读不到）' }, 503);
      const ranSet = new Set(rows.map(r => String(r.uid)));
      const expSet = new Set(expected);
      const missing = expected.filter(u => !ranSet.has(u));
      const extra = [...ranSet].filter(u => !expSet.has(u));
      return json({ ok: true, day: day, pool: poolQ, expected: expected.length, ran: ranSet.size,
                    missing_n: missing.length, missing: missing.slice(0, 80), extra_n: extra.length,
                    extra: extra.slice(0, 80), expected_src: expSrc, snap_at: snapAt,
                    pct: expected.length ? Math.round(ranSet.size * 1000 / expected.length) / 10 : 0 });
    }
    // ---- D1 全量对齐（管理员）：把 KV 当前权威数据整表同步到 D1 ----
    if (url.pathname === '/api/d1_sync' && request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400); }
      const c = await cfg();
      if (!c.adminPass || body.pass !== c.adminPass) return json({ message: '管理密码错误' }, 403);
      if (!d1ok()) return json({ message: 'D1 未绑定' }, 503);
      const master = await mergePoolKV();   // 必须读 KV 原文，否则等于 D1 对齐 D1
      let ok = 0, skip = 0, fail = 0;
      for (const e of master) {
        if (e.uid == null || String(e.uid) === '') { skip++; continue; }
        if (await d1Upsert(e)) ok++; else fail++;
      }
      const live = new Set(master.filter(e => e.uid != null).map(e => String(e.uid)));
      const rows = await d1All('SELECT uid FROM accounts WHERE pool=?', [POOL_NAME]);
      // 2026-11-06：读失败时 rows 为 null，绝不能当成「D1 是空的」继续算差集（会静默返回 removed:0）。
      if (!rows) return json({ message: 'D1 查询失败（accounts 读不到），已中止对齐' }, 503);
      // 'name:xxx' 是「没有 uid 的老条目」的占位主键，不在 live 里但绝不能删。
      const gone = rows.filter(r => !String(r.uid).startsWith('name:') && !live.has(String(r.uid)));
      await Promise.all(gone.map(r => d1Run('DELETE FROM accounts WHERE pool=? AND uid=?', [POOL_NAME, String(r.uid)])));
      try { await refreshPoolSnap(); } catch (e) {}   // D1 全表刚被重写 → 同步刷新应急快照
      return json({ ok: true, pool: POOL_NAME, kv: master.length, synced: ok, skipped: skip,
                    failed: fail, removed: gone.length });
    }
    // ---- 管理端账号维护（本地管理页专用）：删除 / 修改（CK、邮箱、歌曲、有效期、暂停跨群）----
    if (url.pathname === '/api/admin/entry' && request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
      } });
    }
    if (url.pathname === '/api/admin/entry' && request.method === 'POST') {
      const CORS = { 'Access-Control-Allow-Origin': '*' };
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400, CORS); }
      const c = await cfg();
      if (!c.adminPass) return json({ message: '尚未设置管理密码' }, 503, CORS);
      if (!body.pass || body.pass !== c.adminPass) return json({ message: '管理密码错误' }, 403, CORS);
      // 2026-10-22：编辑逻辑抽成 applyEntryEdit，供本路由与跨群对等接口 /api/peer/entry 共用（行为不变）
      return applyEntryEdit(body);
    }
    if (url.pathname === '/api/join_manual' && request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400); }
      const c = await cfg();
      const gp2 = groupPassCheck(c, body);
      if (!gp2.ok) return json({ message: gp2.msg }, gp2.status);
      // 账号池满员闸口（按池计数，防止绕过网页登记直接灌号）
      const isG2 = true; // 定制版 worker：固定按二群闸口（POOL_LIMIT_G2）计数
      const myLimit = groupLimitOf(c, isG2);
      const _m2 = await mergePool();
      const grpUsed = activePoolSize(_m2);   // 排除已过期未清的号，口径一致
      if (grpUsed >= myLimit) return json({ message: '本群名额已满（上限 ' + myLimit + ' 人），暂停登记。已有账号的互听和签到不受影响，请稍后再试或联系群主。' }, 429);
      const mu = (body.musicU || '').trim();
      if (!mu) return json({ message: '请填写 MUSIC_U' }, 400);
      // 2026-10-20 定制版：邮箱改选填——留空也能登记，填了才校验格式
      const email = (body.email || '').trim();
      if (email) { const ebMail = emailBad(email); if (ebMail) return json({ message: ebMail + '（可留空，留空则不发邮件通知）' }, 400); }
      const v = await validateCookie(mu);
      if (!v.ok) return json({ message: v.msg }, 400);
      // 2026-10-26 修复（与协同版一致）：平台校验接口不可达时 validateCookie 会编造 uid 放行，
      // 编造值与真实 uid 不同 → 恢复后同一账号可能重复登记，且任意 80+ 位 hex 都能占名额。
      // 该兜底只对管理员通道开放（带管理口令提交）。
      if (v.provisional) {
        const isAdminReg = !!(c.adminPass && String(body.pass || '') === c.adminPass);
        if (!isAdminReg) {
          return json({ message: '平台校验接口暂时不可达（' + (v.diag || '网络异常') + '），为避免登记出错号，请稍后重试。' }, 503);
        }
      }
      const song = await resolveSong(body.link);
      if (!song.ok) return json({ message: song.msg }, 400);
      let expQ = parseExpInput(body.exp);
      if (!expQ.ok) return json({ message: '有效期格式不对：填天数(如730)、日期(2028-10-18)或"永久"（不填=永久）' }, 400);
      const phoneRaw = (body.phone || '').replace(/[^0-9]/g, '');
      const phone = /^1\d{10}$/.test(phoneRaw) ? phoneRaw : '';
      const rcd2 = await regCfg();
      const pld2 = planOf(rcd2, body.plan);
      /* 2026-11-11：套餐与 exp 打架时以套餐为准（与 hz 同款兜底，只拦「张冠李戴」）。
         旧版 APK 换套餐后 exp 框不重算（选 1年 还送 730 天），而下面 ent.exp 无条件信
         客户端。只在「exp 是纯天数 + 恰好等于另一档套餐的天数 + 不等于所选套餐天数」
         时改按所选套餐重算；手填任意天数、日期、永久，一律照旧放行。 */
      if (expQ.ok && pld2 && /^\d{1,4}$/.test(String(body.exp == null ? '' : body.exp).trim())) {
        const dIn = parseInt(String(body.exp).trim(), 10);
        if (dIn !== pld2.days && (rcd2.plans || []).some(p => p.days === dIn)) {
          console.warn('join_manual exp/plan 不符，按套餐重算:', dIn, '->', pld2.label);
          expQ = { ok: true, exp: pld2.exp };
        }
      }
      const ent = { ck: 'MUSIC_U=' + mu, song: song.song, added: beijingDateTime(), name: phone || ('qr:' + v.uid), uid: v.uid, email: email, phone: phone, grp: isG2 ? 2 : 1, exp: expQ.exp || (pld2 ? pld2.exp : undefined),
        agent: normAgent(body.agent), plan: pld2 ? pld2.label : normAgent(body.plan).slice(0, 8) };
      const r = await addEntry(ent);
      if (!r.ok) return json({ ok: false, message: r.msg }, 400);
      // 2026-10-29 写后自检（与协同版逐字一致）：D1 没落库就不再回「登记成功」。
      let d1Confirmed = null;   // null = 没法确认（D1 查询本身失败，不当成登记失败）
      if (d1ok()) {
        const keyName = phone || ('qr:' + v.uid);
        // 2026-11-08：用 d1FindDup 回查（两条单条件查询走索引），原来是 OR 全池扫。
        const probe = () => d1FindDup(String(v.uid), keyName);
        let chk = await probe();
        if (chk && !chk.length) {
          console.error('登记后 D1 查不到，补写一次:', String(v.uid));
          await d1Upsert(ent);
          chk = await probe();
        }
        if (chk) d1Confirmed = chk.length > 0;
        if (d1Confirmed === false) {
          return json({ ok: false, message: '这次没能写进数据库（号池刚好抖了一下）。请再点一次登记，不会重复占名额。' }, 503);
        }
      }
      // 2026-11-06 晚：定制群不参与邮件通知（用户指定，只发主群）——登记不再入队。
      // mailEnqueue 定义保留但不调用；到期提醒在主群 /api/mail_scan 里已按 pool=主群 过滤。
      let msg = '登记成功，次日生效。';
      if (v.provisional) msg += '（注：网易校验接口暂时不可达[' + (v.diag || '') + ']，已跳过在线校验；明天任务会自动复验）';
      return json({ ok: true, uid: String(v.uid), name: phone || ('qr:' + v.uid), pool: POOL_NAME, d1: d1Confirmed === true, message: msg });
    }
    // ---- 补录/修改通知邮箱（老号自助通道，只改 email 一个字段，其余原样）----
    if (url.pathname === '/api/updatemail' && request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400); }
      const c = await cfg();
      const gp3 = groupPassCheck(c, body);
      if (!gp3.ok) return json({ message: gp3.msg }, gp3.status);
      // 2026-10-26 补频控（与协同版一致）：本接口只要手机号对得上就能改邮箱，没有任何验证。
      // 不能加验证码（会打断正常补录），但必须挡住脚本批量撞号：按出口 IP 每天 20 次。
      const ip = String(request.headers.get('CF-Connecting-IP') || 'unknown').slice(0, 64);
      let hits = await d1Hit('um', ip + ':' + beijingDate());
      if (hits === null) {
        try {
          const rk = 'um:' + ip + ':' + beijingDate();
          const cnt = parseInt(await POOL.get(rk), 10) || 0;
          hits = cnt + 1;
          if (cnt < 20) await POOL.put(rk, String(hits), { expirationTtl: 172800 });
        } catch (e) { hits = 0; }
      }
      if (hits > 20) return json({ message: '今天修改邮箱的次数过多，请明天再试或联系群主。' }, 429);
      const email = (body.email || '').trim();
      const ebMail = emailBad(email);
      if (ebMail) return json({ message: ebMail }, 400);
      const phone = (body.phone || '').replace(/[０-９]/g, c => String.fromCharCode(c.charCodeAt(0) - 65248)).replace(/[^0-9]/g, '');
      const mu = (body.mu || '').trim();
      if (!phone && !mu) return json({ message: '请填写手机号或 MUSIC_U（至少填一个）' }, 400);
      const master = await mergePool();
      let target = null;
      if (mu) {
        const v = await validateCookie(mu);
        if (!v.ok) return json({ message: v.msg }, 400);
        target = master.find(e => e.uid != null && String(e.uid) === String(v.uid)) || null;
      } else {
        target = master.find(e => e.name === phone) || null;
      }
      if (!target) return json({ message: '没有找到你的登记记录：请检查手机号/MUSIC_U 是否填错；如果还没登记过，请用上方的登记方式。' }, 404);
      target.email = email;
      // 与 addEntry 同一套写入机制：独立键权威写 + master 缓存刷新 + 同步账号池 Secrets
      await POOL.put(entryKeyOf(target), JSON.stringify(target));
      // 2026-10-22 修复：读路径全走 D1，这里原先只写 KV → 成员改的邮箱次日被 D1 旧值覆盖回去
      if (!(await d1Upsert(target))) {
        console.error('改邮箱的 D1 镜像失败（KV 已写入，可用 /api/resync 补齐）');
      }
      const updated = master.map(e => entryKeyOf(e) === entryKeyOf(target) ? target : e);
      // master 缓存不再回写（2026-10-22）：读者全走 D1，entry: 独立键才是权威
      await pushPool(updated);
      try { await refreshPoolSnap(); } catch (e) {}
      return json({ message: '已保存：' + email + '。之后账号有变化，会发邮件到这个邮箱。' });
    }
    /* ===== 2026-11-12：换绑登录（ckswap）=====
       适用：号还在池里、CK 本身有效，但这条会话被网易单独标记（自动发动态 code=250）。
       dz 没有扫码登记链接体系（那是 hz 的 reg_tokens//r/），按本群习惯走「粘贴 MUSIC_U + 群口令」：
       号主从浏览器复制一条全新的 MUSIC_U 粘进来，服务端校验后原地替换 ck。
       安全设计：新 CK 校验出的 uid 必须能在号池里找到号 —— 换绑的是「扫/粘的那个账号自己」，
       粘别人的 CK 只能换别人自己的号（而且需要他的 CK），不存在替别人换绑的攻击面。
       只动 ck，不动套餐/有效期/歌曲/邮箱，不写台账；d1Upsert 在 ck 变化时自动清 relogin_at。 */
    if (url.pathname === '/api/ckswap' && request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch (e) { return json({ ok: false, message: '参数错误' }, 400); }
      const c = await cfg();
      const gpC = groupPassCheck(c, body);
      if (!gpC.ok) return json({ ok: false, message: gpC.msg }, gpC.status);
      /* 频控：独立桶 cks，按出口 IP 每天 20 次（与改邮箱同量级，防脚本批量试） */
      const ipC = String(request.headers.get('CF-Connecting-IP') || 'unknown').slice(0, 64);
      let hitsC = await d1Hit('cks', ipC + ':' + beijingDate());
      if (hitsC === null) {
        try {
          const rkC = 'cks:' + ipC + ':' + beijingDate();
          const cntC = parseInt(await POOL.get(rkC), 10) || 0;
          hitsC = cntC + 1;
          if (cntC < 20) await POOL.put(rkC, String(hitsC), { expirationTtl: 172800 });
        } catch (e) { hitsC = 0; }
      }
      if (hitsC > 20) return json({ ok: false, message: '今天换绑次数太多了，请明天再试或联系群主。' }, 429);
      const muC = String(body.musicU || body.mu || '').trim();
      if (!muC) return json({ ok: false, message: '请粘贴新的 MUSIC_U（怎么拿看页面上方的说明）' }, 400);
      const vC = await validateCookie(muC);
      if (!vC.ok) return json({ ok: false, message: vC.msg || '这条 MUSIC_U 已失效，请重新复制一份' }, 400);
      if (vC.provisional) {
        return json({ ok: false, message: '网易校验接口暂时不可达（' + (vC.diag || '网络异常') + '），没法核对账号，请稍后重试' }, 503);
      }
      const masterC = await mergePool();
      const tgtC = masterC.find(e => e && e.uid != null && String(e.uid) === String(vC.uid)) || null;
      if (!tgtC) {
        return json({ ok: false, message: '这个网易云账号不在号池里（可能已掉线被清理，或还没登记过）。换绑只给已登记的号用。' }, 404);
      }
      tgtC.ck = 'MUSIC_U=' + muC;
      if (tgtC.relogin) tgtC.relogin = 0;
      let kvOkC = true;
      try { await POOL.put(entryKeyOf(tgtC), JSON.stringify(tgtC)); }
      catch (e) { kvOkC = false; console.error('换绑 KV 写失败（继续走 D1）:', e && e.message); }
      let d1OkC = false;
      try { d1OkC = await d1Upsert(tgtC); } catch (e) { console.error('换绑 D1 镜像失败:', e && e.message); }
      if (!kvOkC && !d1OkC) {
        return json({ ok: false, message: '数据库暂时繁忙，换绑没有完成，请稍后再试一次' }, 503);
      }
      try { await pushPool(masterC.map(e => (e === tgtC ? tgtC : e))); } catch (e) {}
      try { await refreshPoolSnap(); } catch (e) {}
      console.log('换绑CK：' + String(tgtC.name || vC.uid) + '（uid ' + String(vC.uid) + '，D1 ' + (d1OkC ? 'ok' : 'FAIL') + '）');
      return json({ ok: true, uid: String(vC.uid), name: String(tgtC.name || ''),
        message: '换绑成功：这个号的登录凭证已经换成全新的了（有效期、歌曲、邮箱都没动，听歌不受影响）。'
          + '明天开始自动发动态就会用新凭证；建议你在 App 里发一条图文笔记，如果网易弹了安全验证就顺手完成一下。' });
    }
    // ---- 二维码登录通道（实测平台是否放行 CF 机房 IP）----
    // GET /api/qr_key  → 平台申请 unikey
    // GET /api/qr_check?key=xxx → 轮询：800过期/801等待/802已扫/803成功（成功时从 set-cookie 提取 MUSIC_U 放进 JSON 返回）
    if (url.pathname === '/api/qr_key' && request.method === 'GET') {
      const r = await fetch(BASE + '/api/login/qrcode/unikey', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': UA, 'Referer': BASE + '/' },
        body: 'type=1',
      });
      const text = await r.text();
      return new Response(text, { status: r.status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });
    }
    if (url.pathname === '/api/qr_check' && request.method === 'GET') {
      const key = (url.searchParams.get('key') || '').trim();
      if (!key) return json({ message: '缺少 key' }, 400);
      const r = await fetch(BASE + '/api/login/qrcode/client/login?key=' + encodeURIComponent(key) + '&type=1', {
        headers: { 'User-Agent': UA, 'Referer': BASE + '/' },
      });
      const text = await r.text();
      let out = text;
      try {
        const j = JSON.parse(text);
        if (j.code === 803) {
          const sc = r.headers.get('set-cookie') || '';
          const m = sc.match(/MUSIC_U=([^;]+)/);
          j.musicU = m ? m[1] : '';
          out = JSON.stringify(j);
        }
      } catch (e) { /* 非 JSON（被风控页拦截）原样返回，前端据此判失败 */ }
      return new Response(out, { status: r.status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });
    }
    // 隐藏管理接口：用群口令保护，从 KV 主表重新把 NB_POOL_1..5 推回 GitHub Secrets（KV 丢失/Secrets 异常时一键恢复）
    if (url.pathname === '/api/resync' && request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400); }
      const c = await cfg();
      // 2026-10-22：补 `!c.groupPass` —— 以前 KV 里没配 GROUP_PASS 时，body.pass="" 即可通过
      if (!adminPassOk(c, body.pass)) return json({ message: '管理口令错误' }, 403);
      let master = await mergePool();
      const pushRes = await pushPool(master, true);   // 强制推：resync 就是「现在就要一份全量快照到 Secrets」
      return json({ message: `已从 KV 重新同步 ${master.length} 条到 GitHub Secrets（NB_POOL_1..${(pushRes && pushRes.slots) || 0}，片数按号池体积自动伸缩）。` });
    }
    // 失效账号清理：Actions 跑完发现 cookie 失效的号，按 name/uid 从账号池剔除并重写分片
    // 重登提醒回执（2026-11-04 新增，纯新增路由）：report_dead 把「CK 失效但账号还在」的号
    // 通过 relogin 字段回给 run.py，run.py 直邮成功后调这里写 relogin_at ——
    // 既做「只发一封」的去重标记，也让 buildPlanFrom 把这号摘出听众环。
    if (url.pathname === '/api/relogin_mailed' && request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400); }
      const c = await cfg();
      if (!adminPassOk(c, body.pass)) return json({ message: '管理口令错误' }, 403);
      if (!d1ok()) return json({ ok: false, message: 'D1 未绑定' }, 503);
      const names = (Array.isArray(body.names) ? body.names : []).map(x => String(x)).filter(Boolean).slice(0, 100);
      if (!names.length) return json({ ok: true, wrote: 0 });
      const stamp = new Date().toISOString();
      let wrote = 0;
      for (const nm of names) {
        try {
          await d1Run('UPDATE accounts SET relogin_at=? WHERE pool=? AND (name=? OR uid=?)',
                      [stamp, POOL_NAME, nm, nm]);
          wrote++;
        } catch (_e) {}
      }
      return json({ ok: true, wrote: wrote });
    }
    // ---- 2026-11-09：CK 失效超时清理入口（对端 hz 主 cron 调 / 人工排障）----
    // 本 worker 没有 scheduled handler，定时全靠 GitHub；这条路由让主群 cron 能隔空触发。
    // 认证同时接受 peerKey（跨群）与 adminPass（管理）。
    if (url.pathname === '/api/relogin_sweep' && request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400); }
      const c = await cfg();
      const byPeer = await peerPassOk(body.pass);
      if (!byPeer && !adminPassOk(c, body.pass)) return json({ message: '口令错误' }, 403);
      const r = await pruneStaleRelogin(body.days);
      return json(r, r.ok === false ? 503 : 200);
    }
    // 直邮回执（2026-11-03 新增，纯新增路由）：run.py / signin.py 真把「账号信息过期」
    // 邮件发出去之后调这里，把 dead_notice 里对应条目直接标成 sent，
    // 免得 notify_dead.py 隔 12 小时再给同一个号主发第二封一样的邮件。
    // 只动 state='pending' 的行，重复调用无副作用；认证口径与 /api/report_dead 一致。
    if (url.pathname === '/api/dead_mailed' && request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400); }
      const c = await cfg();
      if (!adminPassOk(c, body.pass)) return json({ message: '管理口令错误' }, 403);
      if (!d1ok()) return json({ ok: false, message: 'D1 未绑定' }, 503);
      const poolN = String(body.pool || POOL_NAME);
      const stamp = bjStamp();
      let n = 0;
      for (const nm of (body.names || []).slice(0, 200)) {
        const s = String(nm || '').trim();
        if (!s) continue;
        try {
          const ok = await d1Run("UPDATE dead_notice SET state='sent',sent_at=?,skip_reason=? WHERE pool=? AND state='pending' AND name=?",
            [stamp, '直邮已发', poolN, s]);
          if (ok) n++;   // d1Run 内部吞异常只回 false，按返回值计数才看得出 SQL 是否真跑通
        } catch (_e) {}
      }
      return json({ ok: true, marked: n, pool: poolN });
    }
    if (url.pathname === '/api/report_dead' && request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400); }
      const c = await cfg();
      if (!adminPassOk(c, body.pass)) return json({ message: '管理口令错误' }, 403);
      const deadSet = new Set((body.dead || []).map(x => String(x)));
      if (!deadSet.size) return json({ message: '没有需要清理的账号。' });
      const master = await mergePool();
      const before = master.length;
      const deadEntries = master.filter(e => deadSet.has(String(e.name)) || deadSet.has(String(e.uid)));
      if (!deadEntries.length) return json({ message: `没有匹配到账号（号池 ${before} 个）。` });

      // ---- 死号判定（2026-10-23 改版：客户端重试 + 立即删除）----
      // 旧逻辑（2026-10-22）：第一次判死只打 suspect_at，隔 18~36 小时下一轮再判死才真删。
      // 问题：号主要白等一整天，期间客服也没法提前帮他重新登记。
      // 新逻辑：客户端（run.py）判死前已重试 3 次（要求至少 2 次明确失效），确认后带
      // confirm=true 上报 → 服务端直接删号，客户端随即发「账号信息过期」邮件。
      // 不带 confirm 的旧客户端仍走 suspect_at 双重确认，向后兼容。
      const forceConfirm = body.confirm === true;
      // 2026-11-04：forceConfirm 也照常查一遍，susMap 给不带 confirm 的老客户端用。
      // 2026-11-09：不再需要 relMap（「保留 + 等号主重登」这条支路已取消，改为验 CK 后立即删）。
      let susRows = null;
      try { susRows = await d1All('SELECT uid,suspect_at FROM accounts WHERE pool=?', [POOL_NAME]); } catch (_e) { susRows = null; }
      const susMap = {};
      if (susRows) for (const r of susRows) {
        susMap[String(r.uid)] = String(r.suspect_at || '');
      }
      const nowMs = Date.now();
      const suspects = [], confirmed = [];
      for (const e of deadEntries) {
        if (forceConfirm) { confirmed.push(e); continue; }   // 客户端已重试确认 → 直接删
        if (!susRows) { suspects.push(e); continue; }        // D1 读不到 → 无法确认，保守只打标不删
        const prev = susMap[String(e.uid)] || '';
        const t = prev ? Date.parse(prev) : NaN;
        const ageH = isNaN(t) ? -1 : (nowMs - t) / 3600000;
        if (ageH >= 18 && ageH <= 36) confirmed.push(e); else suspects.push(e);
      }
      const stamp = new Date(nowMs).toISOString();
      if (susRows) {
        for (const e of suspects) {
          await d1Run('UPDATE accounts SET suspect_at=? WHERE pool=? AND uid=?', [stamp, POOL_NAME, String(e.uid)]);
        }
      }
      // 2026-10-29 修复「删失败也给号主发过期邮件」：
      // 旧顺序是「先删 KV 键 → 再 d1Delete」，而 d1Delete 失败只 return false、不抛异常，
      // 外层 try/catch 拦不到，deleted 依旧原样返回全部名单 → 号还在池里播，号主已收到过期邮件。
      // 现在先删 D1，只有真删成功的才删 KV 键 / 进墓碑 / 计进 deleted。
      // ---- 2026-11-09 口径：客户端反复确认失效 → 立刻删，服务端不再插「账号还在就保留」的复核 ----
      // 删掉旧 B 方案的原因：它用别的活号查 user/detail/<uid>，只能证明「账号还在网易」，
      // 证明不了「这个 CK 还能用」。而最常见的失效恰恰是「CK 死了、账号还在」（换设备/被顶号），
      // 于是号被保留 + 发「请重登」，号主不理就无限挂着（11-09 手工清 6 个 dz 号，最短挂 5 天）。
      // 客户端的确认已经够硬（run.py.login_by_cookie）：先 weapi account/get 拿 profile，
      // 拿不到再用 v1 每日推荐二次验证，必须「code=200 但 0 首」才算明确失效，且 3 次里 2 次明确失败。
      // 服务端「再验一次 CK」的做法 2026-11-09 实测不可行：明文 account/get 与 v1 每日推荐
      // 对池内随机 6 个健康号全部回「未登录/0 首」（当天 dead_log 只删 8 个），没有区分度，
      // 再加只会制造误判，所以整段删掉。
      // 唯一保留的防线：单次最多删 MAX_DEL 个，防止客户端一次 bug 把全池报成死号。
      const reloginNotify = [];   // 不再产生；字段留着只为兼容 run.py 的解析
      let keptUnknown = 0;
      const keptNames = [];
      const MAX_DEL = 40;
      if (confirmed.length > MAX_DEL) {
        const over = confirmed.splice(MAX_DEL);
        keptUnknown = over.length;
        for (const e of over) keptNames.push(e.name || String(e.uid));
        console.warn('单次上报 ' + (MAX_DEL + keptUnknown) + ' 个死号，超过上限，本轮只删前 ' + MAX_DEL + ' 个，其余下轮再判');
      }
      const keepNote = keptNames.length
        ? '；另有 ' + keptNames.length + ' 个超过单次删除上限 ' + MAX_DEL + '，本轮未处理、下轮再判：' + keptNames.join('、')
        : '';
      const hasD1 = d1ok();
      const delRes = await Promise.all(confirmed.map(async e => {
        if (!hasD1) return { e: e, ok: true };      // D1 未绑定：纯 KV 模式，按成功处理
        let ok = false;
        try { ok = (await d1Delete(e)) === true; } catch (_e) { ok = false; }
        return { e: e, ok: ok };
      }));
      const reallyGone = delRes.filter(x => x.ok).map(x => x.e);
      const delFail = delRes.filter(x => !x.ok).map(x => x.e);
      if (delFail.length) {
        console.error('D1 删除失败（这些号保留在池内、不发信）: ' + delFail.map(e => e.name || e.uid).join('、'));
      }
      // 删除走独立键（单键删除，无竞态），并记墓碑防缓存复活；再刷新 master 缓存
      await Promise.all(reallyGone.map(async e => { try { await POOL.delete(entryKeyOf(e)); } catch (_e) {} }));
      const deadEkeys = reallyGone.map(e => entryKeyOf(e));
      if (deadEkeys.length) {
        try {
          const log = new Set(await getDeadLog());
          for (const k of deadEkeys) log.add(k);
          // 只留最近 500 条，防止无限增长
          await POOL.put('dead_log', JSON.stringify([...log].slice(-500)));
        } catch (e) {}
      }
      // 2026-11-03 补缺口：自动删号（cookie_invalid）以前完全不进 dead_notice 队列 ——
      //   号主通知全靠 run.py 回执后直邮，直邮没配好/失败就一封都发不出去（11-03 全池扫 94 个
      //   job 日志，找不到任何「已直邮号主」）。现在删成功的号一律入队 pending：
      //   run.py / signin.py 直邮成功会回调 /api/dead_mailed 把这条标成 sent；
      //   没标成的由主群 notify_dead.py 隔 12 小时兜底发（两群共用同一张 D1 表，pool 各自独立）。
      //   12 小时窗口顺带挡掉「删完当天就重登」的误报（判据在 /api/dead_pending 的 skip_returned）。
      let queued = 0;
      for (const e of reallyGone) {
        try { if (await d1QueueNotice(e)) queued++; } catch (_e) {}
      }
      await d1LogDead(reallyGone, 'cookie_invalid');
      const gone = new Set(deadEkeys);
      const after = master.filter(e => !gone.has(entryKeyOf(e)));
      // master 缓存不再回写（2026-10-22）：读者全走 D1，entry: 独立键才是权威
      await pushPool(after);
      try { await refreshPoolSnap(); } catch (e) {}
      const nm = arr => arr.map(e => e.name || e.uid).join('、');
      // deleted：真正被删掉的号名。run.py 靠它决定「给谁发过期邮件」——
      // 只有删成功了才发，避免「邮件说已删除、号其实还在池里」。
      const deleted = reallyGone.map(e => e.name || String(e.uid));
      const failNote = delFail.length
        ? `；${delFail.length} 个 D1 删除失败（${delFail.map(e => e.name || e.uid).join('、')}）仍留在池内，未发信，下轮会重试`
        : '';
      return json({ ok: true, deleted: deleted, relogin: reloginNotify,
        message: `本次确认清理 ${confirmed.length} 个${confirmed.length ? '（' + nm(confirmed) + '）' : ''}`
        + `，实际删除 ${reallyGone.length} 个${failNote}${keepNote}；`
        + `新增疑似 ${suspects.length} 个（需下一轮再次判死才删除${suspects.length ? '：' + nm(suspects) : ''}），`
        + `剩余 ${after.length} 个。` });
    }
    // ---- 进阶控制台对等接口（2026-10-22 新增）：主群控制台（xx1031.xyz/console）需要读/编定制群账号 ----
    //      口令 = KV 键 PEER_KEY（2026-10-26 起；未配置才回退旧的 PEER_PASS 对穿）；只回展示字段，绝不下发 ck。
    if (url.pathname === '/api/peer/pool' && request.method === 'GET') {
      const CORS = { 'Access-Control-Allow-Origin': '*' };
      const pk0 = await peerKey();
      if (!pk0 && !cleanKV(await POOL.get('PEER_PASS'))) return json({ message: '未开启跨群对穿：请在 KV 添加 PEER_KEY 键' }, 503, CORS);
      if (!(await peerPassOk(url.searchParams.get('pass')))) return json({ message: '口令错误' }, 403, CORS);
      // 2026-10-22：主群控制台每次刷新都会调这个接口，原来是「读 + 清理 + 推 Secret」三合一，
      // 现在只读（D1 一条 SELECT）。
      const master = await mergePool();
      const entries = master.map(e => ({
        name: e.name || '', uid: e.uid != null ? String(e.uid) : '',
        song: e.song != null ? String(e.song) : '', added: e.added || '',
        email: e.email || '', phone: e.phone || '', noListen: !!e.noListen, exp: e.exp || '',
        // 2026-10-27：主群控制台要按客服/套餐筛选，定制群的号也必须带上这两项
        agent: e.agent || '', plan: e.plan || '',
        // 2026-11-01：公益号标记（主群控制台据此显示「公益号」徽章）
        pub: !!e.pub,
      }));
      return json({ ok: true, entries: entries }, 200, CORS);
    }
    // 跨群编辑（删除/修改），与 /api/admin/entry 完全同一套逻辑，仅鉴权换成对穿口令 PEER_KEY
    if (url.pathname === '/api/peer/entry' && request.method === 'POST') {
      const CORS = { 'Access-Control-Allow-Origin': '*' };
      let body;
      try { body = await request.json(); } catch (e) { return json({ message: '参数错误' }, 400, CORS); }
      const pk1 = await peerKey();
      if (!pk1 && !cleanKV(await POOL.get('PEER_PASS'))) return json({ message: '未开启跨群对穿：请在 KV 添加 PEER_KEY 键' }, 503, CORS);
      if (!body.pass || !(await peerPassOk(body.pass))) return json({ message: '口令错误' }, 403, CORS);
      return applyEntryEdit(body);
    }
    return json({ message: 'not found' }, 404);
}

function json(o, status = 200, extraHeaders) { return new Response(JSON.stringify(o), { status, headers: Object.assign({ 'Content-Type': 'application/json' }, extraHeaders || {}) }); }

// ---- 账号编辑共用逻辑（2026-10-22 从 /api/admin/entry 抽出，行为与原实现逐行一致）----
// 供 /api/admin/entry（管理密码）与 /api/peer/entry（跨群对穿口令）两个路由调用。
async function applyEntryEdit(body) {
  const CORS = { 'Access-Control-Allow-Origin': '*' };
  const master = await mergePool();
  const target = master.find(e =>
    (body.uid != null && String(body.uid) !== '' && e.uid != null && String(e.uid) === String(body.uid)) ||
    (body.name && String(e.name) === String(body.name)));
  if (!target) return json({ message: '没找到该账号（可能已被删除）' }, 404, CORS);
  if (body.action === 'delete') {
    // 2026-10-29：改成「先删 D1，成功才删 KV」。旧顺序先删 KV、D1 删失败只打日志 →
    // D1 那行还在，下一次 mergePool 会把它悄悄读回来（控制台已显示已删除），
    // 而且通知队列照排，号主会收到「账号信息过期」。失败直接报错，不留半删状态。
    if (d1ok()) {
      let ok = false;
      try { ok = (await d1Delete(target)) === true; } catch (e) { ok = false; }
      if (!ok) return json({ message: 'D1 删除失败，账号未删除，请稍后重试' }, 500, CORS);
    }
    await POOL.delete(entryKeyOf(target));
    try {
      const log = new Set(await getDeadLog());
      log.add(entryKeyOf(target));
      await POOL.put('dead_log', JSON.stringify([...log].slice(-500)));
    } catch (e) {}
    const kept = master.filter(e => e !== target);
    await d1LogDead([target], 'manual');
    // 2026-10-26：同时进「通知号主」判定队列（12 小时后判是不是真删，判定在 cron-relay 侧）。
    // 纯新增的一行写入，不影响任何既有行为；写失败也只是少一封邮件。
    try { await d1QueueNotice(target); } catch (e) { console.error('通知队列写入失败:', e && e.message); }
    // master 缓存不再回写（2026-10-22）：读者全走 D1，entry: 独立键才是权威
    await pushPool(kept);
    try { await refreshPoolSnap(); } catch (e) {}
    return json({ ok: true, message: '已删除账号 ' + (target.name || target.uid) }, 200, CORS);
  }
  if (body.action === 'update') {
    const changes = [];
    if (body.ck != null && String(body.ck).trim() !== '') {
      let mu = String(body.ck).trim();
      const mm = mu.match(/MUSIC_U=([^;\s"']+)/);
      if (mm) mu = mm[1];
      if (!/^[A-Za-z0-9%_-]{20,}$/.test(mu)) return json({ message: 'MUSIC_U 格式不对（应为 32 位左右的长字符串）' }, 400, CORS);
      const v = await validateCookie(mu);
      if (!v.ok) return json({ message: '新 CK 校验未通过：' + v.msg }, 400, CORS);
      target.ck = 'MUSIC_U=' + mu;
      changes.push('CK');
    }
    if (body.link != null && String(body.link).trim() !== '') {
      const song = await resolveSong(String(body.link));
      if (!song.ok) return json({ message: song.msg }, 400, CORS);
      target.song = song.song;
      changes.push('歌曲');
    }
    if (body.email != null && String(body.email).trim() !== '') {
      const em = String(body.email).trim();
      const ebMail = emailBad(em);
      if (ebMail) return json({ message: ebMail }, 400, CORS);
      target.email = em;
      changes.push('邮箱');
    }
    if (body.exp != null && String(body.exp).trim() !== '') {
      const x = String(body.exp).trim();
      if (x === 'forever' || x === '永久') { delete target.exp; changes.push('有效期=永久'); }
      else if (/^\d{4}-\d{2}-\d{2}$/.test(x)) { target.exp = x; changes.push('有效期=' + x); }
      else if (/^\d{1,4}$/.test(x)) { const d = beijingDatePlus(parseInt(x, 10)); target.exp = d; changes.push('有效期=' + x + '天(' + d + '止)'); }
      else return json({ message: '有效期格式不对：填天数(如30)、日期(2026-12-31)或"永久"' }, 400, CORS);
    }
    if (body.noListen !== undefined && body.noListen !== null) {
      target.noListen = !!body.noListen;
      changes.push(body.noListen ? '暂停互听(只收不听)' : '恢复互听');
    }
    // 2026-11-01：公益号开关（只帮别人听歌 / 自己的歌不再分给别人听 / 不签到）。
    // 只打标记不动 song，改回普通号第二天自动恢复被听。
    if (body.pub !== undefined && body.pub !== null) {
      target.pub = body.pub ? 1 : 0;
      changes.push(body.pub ? '设为公益号(只帮别人听，自己的歌不再分给别人听、也不签到)'
                            : '恢复普通号(参加互听+签到)');
    }
    // 2026-10-27：客服标签 / 套餐档位（主群控制台跨群编辑时会带过来）。留空=不改。
    if (body.agent != null && String(body.agent).trim() !== '') {
      target.agent = normAgent(body.agent);
      changes.push('客服=' + (target.agent || '未标注'));
    }
    if (body.plan != null && String(body.plan).trim() !== '') {
      const rcP = await regCfg();
      const plP = planOf(rcP, body.plan);
      target.plan = plP ? plP.label : normAgent(body.plan).slice(0, 8);
      changes.push('套餐=' + target.plan);
    }
    if (!changes.length) return json({ message: '没有要修改的内容（各栏留空=不改）' }, 400, CORS);
    await POOL.put(entryKeyOf(target), JSON.stringify(target));
    // 2026-10-22：D1 已是唯一读路径，镜像写失败必须显式告诉调用方 ——
    // 否则界面显示"已修改"，第二天读 D1 又变回旧值，谁都不知道出了事。
    let d1okEdit = false;
    try { d1okEdit = await d1Upsert(target); } catch (e) { console.error('D1 修改镜像失败:', e && e.message); }
    // master 缓存不再回写（2026-10-22）：读者全走 D1，entry: 独立键才是权威
    await pushPool(master);
    try { await refreshPoolSnap(); } catch (e) {}
    return json({ ok: true, d1: !!d1okEdit,
      message: '已修改 ' + (target.name || target.uid) + '：' + changes.join('、')
        + (d1okEdit ? '' : '（⚠️ D1 镜像写入失败：KV 已保存，请稍后调 /api/resync 补齐）') }, 200, CORS);
  }
  return json({ message: '未知操作' }, 400, CORS);
}

const INDEX_HTML = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>成员接入</title><style>body{font-family:-apple-system,system-ui,"PingFang SC",sans-serif;background:#f5f6f8;margin:0;padding:24px 12px;display:flex;flex-direction:column;align-items:center;gap:16px}.head{text-align:center;margin-bottom:2px}.page-title{font-size:20px;font-weight:600;color:#3b6d11;margin:0}.page-sub{font-size:13px;color:#666;margin:6px 0 0}.wrap{display:flex;flex-wrap:wrap;gap:18px;justify-content:center;width:100%;max-width:1060px}.card{background:#fff;padding:26px 22px;border-radius:14px;width:330px;min-width:0;box-sizing:border-box;box-shadow:0 2px 12px rgba(0,0,0,.08)}h1{font-size:17px;margin:0 0 4px}h1.alt{color:#b06a00}p{font-size:13px;color:#666;margin:0 0 16px;line-height:1.5}label{display:block;font-size:13px;margin:12px 0 4px;color:#333}input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #ddd;border-radius:8px;font-size:14px}.row{display:flex;gap:8px}.row input{flex:1}button{margin-top:14px;width:100%;padding:11px;border:0;border-radius:8px;background:#3b6d11;color:#fff;font-size:15px;cursor:pointer}button.mini{margin-top:0;width:auto;padding:10px 12px;font-size:13px;background:#5a8f1d;white-space:nowrap}button:disabled{opacity:.55;cursor:default}.msg{margin-top:14px;font-size:13px;min-height:18px;line-height:1.5}.ok{color:#3b6d11}.err{color:#a32d2d}.tip{color:#666}details{margin-top:14px;font-size:12px;color:#666;line-height:1.6}summary{cursor:pointer;color:#3b6d11}code{background:#eee;padding:1px 4px;border-radius:4px}.admin-entry{margin:10px 0 0;font-size:12px}.admin-entry a{color:#3b6d11;text-decoration:none;border-bottom:1px dashed #3b6d11;padding-bottom:1px}.abox{background:#fff;padding:22px;border-radius:14px;box-shadow:0 2px 12px rgba(0,0,0,.08);width:100%;max-width:1060px;box-sizing:border-box}.stats{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 14px}.stat{flex:1;min-width:100px;background:#f2f7ea;border-radius:10px;padding:10px 12px;text-align:center}.stat b{display:block;font-size:20px;color:#3b6d11}.stat span{font-size:12px;color:#666}.stat.warn b{color:#b06a00}.stat.warn{background:#fdf3e3}.tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}.tools input{flex:1;min-width:160px;padding:9px 10px;border:1px solid #ddd;border-radius:8px;font-size:14px}.tools button{margin-top:0;width:auto;padding:9px 14px;font-size:13px}button.gray{background:#888}.twrap{overflow-x:auto;border:1px solid #eee;border-radius:10px}table{border-collapse:collapse;width:100%;font-size:13px}th{background:#f5f6f8;text-align:left;padding:9px 10px;white-space:nowrap;color:#444;border-bottom:1px solid #eee}td{padding:8px 10px;border-bottom:1px solid #f2f2f2;white-space:nowrap}tr:hover td{background:#fafdf5}.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:8px;margin-right:4px}.b-red{background:#fbe4e4;color:#a32d2d}.b-gray{background:#eee;color:#666}.b-yellow{background:#fdf3e3;color:#b06a00}.num{font-family:ui-monospace,Consolas,monospace;color:#555}</style></head><body><div class="head"><h1 class="page-title">成员接入</h1><p class="page-sub">在下方登记新账号；已经登记过的成员，可在下方补录或修改通知邮箱（页面版本 v20261028a）</p><p class="admin-entry"><a href="/admin">群主管理后台</a></p></div><div class="wrap"><div class="card"><h1>成员接入（复制 MUSIC_U）</h1><p>自己从浏览器复制 <code>MUSIC_U</code> 粘贴过来，<b>次日生效</b>。注意：<b>每个账号限登记一首歌</b>，重复登记会被拒绝；<b>号池上限 __POOL_LIMIT__ 人</b>，满员后暂停登记。</p><label>MUSIC_U</label><input id="mu" placeholder="粘贴浏览器里的 MUSIC_U 值"><label>分享链接</label><input id="link2" placeholder="粘贴 APP 内分享的单曲链接"><label>群口令</label><input id="pass2" type="text" placeholder="群内获取的群口令"><label>邮箱（必填）</label><input id="email2" type="text" placeholder="账号有变化时邮件通知你"><button id="btn2">直接登记</button><details><summary>怎么拿到 MUSIC_U？（点开看）</summary>用电脑浏览器打开 <code>https://music.163.com</code> 并登录 → 按 <code>F12</code> → 切到「Application / 应用」标签 → 左侧展开 <code>Cookies</code> → 选 <code>music.163.com</code> → 在右边找到名为 <code>MUSIC_U</code> 的那一行，复制它的「Value / 值」整串粘进来即可。</details><div class="msg tip" id="msg2"></div></div><div class="card"><h1 class="alt">绑定 / 更换通知邮箱</h1><p>之前登记时没填邮箱、或者想换一个邮箱，在这里改一下就行。<b>只改邮箱，其他设置原样不动</b>，之后想再换随时能来改。账号有变化时（比如需要完成一次验证、登录过期），会发邮件到这个邮箱提醒你。</p><label>手机号（用手机号登记过的填这个）</label><input id="pm_phone" inputmode="numeric" maxlength="11" placeholder="登记时用的 11 位手机号"><label>MUSIC_U（复制 MUSIC_U 登记的填这个，与手机号二选一即可）</label><input id="pm_mu" placeholder="登记时粘贴的 MUSIC_U"><label>常用邮箱</label><input id="pm_email" type="text" placeholder="name@qq.com"><label>群口令</label><input id="pm_pass" type="text" placeholder="群内获取的群口令"><button id="btn3">保存邮箱</button><div class="msg tip" id="msg3">手机号和 MUSIC_U 填其中一个就行。</div></div><div class="card"><h1 class="alt">换绑登录（发动态恢复）</h1><p>自动发动态时被网易要求「安全验证」的号，在这里换一条全新的登录凭证。<b>只换凭证：有效期、歌曲、邮箱都不变，不收任何费用</b>，听歌不受影响。操作：用电脑浏览器打开 <code>https://music.163.com</code> 重新登录这个账号（App 里不用退出），按上面登记卡里的方法复制新的 <code>MUSIC_U</code> 粘到这里。</p><label>新的 MUSIC_U</label><input id="cs_mu" placeholder="粘贴重新登录后复制的 MUSIC_U"><label>群口令</label><input id="cs_pass" type="text" placeholder="群内获取的群口令"><button id="btn4">完成换绑</button><div class="msg tip" id="msg4">换绑完成后，建议在 App 里发一条图文笔记；如果网易弹了安全验证，顺手完成一下。</div></div></div><script>const $=id=>document.getElementById(id);function normPhone(s){return (s||'').replace(/[０-９]/g,c=>String.fromCharCode(c.charCodeAt(0)-65248)).replace(/[^0-9]/g,'');}function setMsg(el,t,cls){const m=$(el);m.textContent=t;m.className='msg'+(cls?(' '+cls):'');}$('btn2').onclick=async()=>{const musicU=$('mu').value.trim(),link=$('link2').value.trim(),pass=$('pass2').value.trim(),email=$('email2').value.trim();if(!musicU){setMsg('msg2','请填写 MUSIC_U','err');return;}if(!email){setMsg('msg2','请填写邮箱（用于接收任务验证码与异常提醒）','err');return;}if(!link){setMsg('msg2','请填写歌曲链接','err');return;}setMsg('msg2','处理中…');$('btn2').disabled=true;try{const r=await fetch('/api/join_manual',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({musicU,link,pass,email})});const d=await r.json();if(r.ok){setMsg('msg2',d.message||'登记成功，次日开始。','ok');}else{setMsg('msg2',d.message||'失败','err');}}catch(e){setMsg('msg2','网络错误','err');}$('btn2').disabled=false;};$('btn3').onclick=async()=>{const phone=normPhone($('pm_phone').value),mu=$('pm_mu').value.trim(),email=$('pm_email').value.trim(),pass=$('pm_pass').value.trim();if(!phone&&!mu){setMsg('msg3','手机号和 MUSIC_U 至少填一个','err');return;}if(!email){setMsg('msg3','请填写常用邮箱','err');return;}if(!pass){setMsg('msg3','请先填写群口令','err');return;}setMsg('msg3','正在保存…');$('btn3').disabled=true;try{const r=await fetch('/api/updatemail',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone,mu,email,pass})});const d=await r.json();if(r.ok){setMsg('msg3',d.message||'已保存','ok');}else{setMsg('msg3',d.message||'保存失败','err');}}catch(e){setMsg('msg3','网络错误','err');}$('btn3').disabled=false;};$('btn4').onclick=async()=>{const musicU=$('cs_mu').value.trim(),pass=$('cs_pass').value.trim();if(!musicU){setMsg('msg4','请粘贴新的 MUSIC_U','err');return;}if(!pass){setMsg('msg4','请先填写群口令','err');return;}setMsg('msg4','正在换绑…');$('btn4').disabled=true;try{const r=await fetch('/api/ckswap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({musicU,pass})});const d=await r.json();if(d.ok){setMsg('msg4',d.message||'换绑成功','ok');}else{setMsg('msg4',d.message||'换绑失败','err');}}catch(e){setMsg('msg4','网络错误','err');}$('btn4').disabled=false;};</script></body></html>`;
// 定制版登记页：由 INDEX_HTML（一群原版页）派生——
// 1) 标题/版本标识显示"定制版"，页面不出现任何"二群"字样；
// 2) 去掉群口令输入框与前端口令校验（服务端 groupPassCheck 也已放行）；
// 3) 上限文案写 500（实际闸口为服务端 POOL_LIMIT_G2）；
// 4) 4 个接口请求体带 group:2 且不带 pass。
const INDEX_HTML_DZ = INDEX_HTML
  .replace('<title>成员接入</title>', '<title>成员接入（定制版）</title>')
  .replace('<h1 class="page-title">成员接入</h1>', '<h1 class="page-title">成员接入（定制版）</h1>')
  .replace('（页面版本 v20261028a）', '（页面版本 v20261028a · 定制版）')
  // 2026-10-20 邮箱改为选填：只改定制版页面的文案与前端校验，一群/二群页面（/、/g2）不受影响
  .replace('<label>邮箱（必填）</label><input id="email2"', '<label>邮箱（选填）</label><input id="email2"')
  .replace('if(!email){setMsg(\'msg2\',\'请填写邮箱（用于接收任务验证码与异常提醒）\',\'err\');return;}', 'if(email&&!/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(email)){setMsg(\'msg2\',\'邮箱格式不对，可留空\',\'err\');return;}')
  // 2026-10-22：上限文案改成模板占位符 __POOL_LIMIT__，由请求时按 KV 的 POOL_LIMIT_G2 渲染
  //（原来靠 replace('账号池上限 200 人', '账号池上限 500 人') 硬替换，改了 HTML 文案就会静默失效）
  .replace('<label>群口令</label><input id="pass2" type="text" placeholder="群内获取的群口令">', '')
  .replace('<label>群口令</label><input id="pm_pass" type="text" placeholder="群内获取的群口令">', '')
  .replace('link=$(\'link2\').value.trim(),pass=$(\'pass2\').value.trim(),email=$(\'email2\').value.trim();', 'link=$(\'link2\').value.trim(),email=$(\'email2\').value.trim();')
  .replace('const phone=normPhone($(\'pm_phone\').value),mu=$(\'pm_mu\').value.trim(),email=$(\'pm_email\').value.trim(),pass=$(\'pm_pass\').value.trim();', 'const phone=normPhone($(\'pm_phone\').value),mu=$(\'pm_mu\').value.trim(),email=$(\'pm_email\').value.trim();')
  .replace('if(!pass){setMsg(\'msg3\',\'请先填写群口令\',\'err\');return;}', '')
  .replace('JSON.stringify({musicU,link,pass,email})', 'JSON.stringify({musicU,link,email,group:2})')
  .replace('JSON.stringify({phone,mu,email,pass})', 'JSON.stringify({phone,mu,email,group:2})');

const ADMIN_HTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>号池管理后台</title>
<style>
body{font-family:-apple-system,system-ui,"PingFang SC",sans-serif;background:#f5f6f8;margin:0;padding:24px 12px;display:flex;flex-direction:column;align-items:center;gap:16px}
.head{text-align:center}.page-title{font-size:20px;font-weight:600;color:#3b6d11;margin:0}
.page-sub{font-size:13px;color:#666;margin:6px 0 0}
.abox{background:#fff;padding:22px;border-radius:14px;box-shadow:0 2px 12px rgba(0,0,0,.08);width:100%;max-width:1060px;box-sizing:border-box}
h2{font-size:16px;margin:0 0 4px}
.tip{font-size:12px;color:#999;margin:0 0 14px}
input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #ddd;border-radius:8px;font-size:14px}
button{margin-top:12px;width:100%;padding:11px;border:0;border-radius:8px;background:#3b6d11;color:#fff;font-size:15px;cursor:pointer}
button.gray{background:#999}
button.mini{margin-top:0;width:auto;padding:9px 14px;font-size:13px}
button:disabled{opacity:.55;cursor:default}
.msg{margin-top:12px;font-size:13px;min-height:18px}
.ok{color:#3b6d11}.err{color:#a32d2d}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 14px}
.stat{flex:1;min-width:104px;background:#f2f7ea;border-radius:10px;padding:10px 12px;text-align:center}
.stat b{display:block;font-size:20px;color:#3b6d11}
.stat span{font-size:12px;color:#666}
.stat.warn{background:#fdf3e3}.stat.warn b{color:#b06a00}
.tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}
.tools input{flex:1;min-width:160px}
.twrap{overflow-x:auto;border:1px solid #eee;border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:13px}
th{background:#f5f6f8;text-align:left;padding:9px 10px;white-space:nowrap;color:#444;border-bottom:1px solid #eee}
td{padding:8px 10px;border-bottom:1px solid #f2f2f2;white-space:nowrap}
tr:hover td{background:#fafdf5}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:8px;margin-right:4px}
.b-red{background:#fbe4e4;color:#a32d2d}.b-gray{background:#eee;color:#666}.b-yellow{background:#fdf3e3;color:#b06a00}
.num{font-family:ui-monospace,Consolas,monospace;color:#555}
a.song{color:#3b6d11;text-decoration:none;border-bottom:1px dotted #3b6d11}
</style>
</head>
<body>
<div class="head"><h1 class="page-title">互听群号池管理后台</h1><p class="page-sub">仅群主可访问，页面不显示登录凭证</p></div>

<div class="abox" id="loginBox">
  <h2>管理密码</h2>
  <p class="tip">与群口令相互独立。输入后浏览器会本地记住，过期可点"退出登录"清除。</p>
  <input id="pw" type="password" placeholder="管理密码（ADMIN_PASS）">
  <button id="btn">进入后台</button>
  <div class="msg" id="lm"></div>
</div>

<div class="abox" id="mainBox" hidden>
  <div class="stats" id="stats"></div>
  <div class="tools">
    <input id="q" placeholder="搜索：账号 / 邮箱 / UID / 歌曲ID">
    <button class="mini" id="btnCsv">导出 CSV</button>
    <button class="mini" id="btnCopy">复制未绑邮箱名单</button>
    <button class="mini" id="btnRefresh">刷新</button>
    <button class="mini gray" id="btnOut">退出登录</button>
  </div>
  <div class="twrap">
    <table>
      <thead><tr><th>#</th><th>账号</th><th>UID</th><th>绑定歌曲</th><th>入池日期</th><th>通知邮箱</th><th>标记</th></tr></thead>
      <tbody id="tb"></tbody>
    </table>
  </div>
  <p class="tip" style="margin:12px 0 0">改绑歌曲 / 删除账号 / 换 CK 等写操作请在本地跑「号池管理.bat」，本后台只读，防止误操作。</p>
</div>

<script>
var POOL=[],STATS={};
function $(id){return document.getElementById(id);}
function msg(t,ok){var m=$('lm');m.textContent=t;m.className='msg'+(ok?' ok':' err');}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function login(){
  var p=$('pw').value.trim();
  if(!p){msg('请输入管理密码');return;}
  $('btn').disabled=true;
  fetch('/api/pool',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pass:p})})
  .then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});})
  .then(function(o){
    $('btn').disabled=false;
    if(!o.ok){msg(o.d.message||'管理密码错误');return;}
    try{localStorage.setItem('poolAdminPass',p);}catch(e){}
    POOL=o.d.entries||[];STATS=o.d.stats||{};
    $('loginBox').hidden=true;$('mainBox').hidden=false;
    render();
  }).catch(function(){ $('btn').disabled=false; msg('网络错误，请重试'); });
}
$('btn').onclick=login;
$('pw').onkeydown=function(e){if(e.key==='Enter')login();};
$('btnOut').onclick=function(){try{localStorage.removeItem('poolAdminPass');}catch(e){}location.reload();};
$('btnRefresh').onclick=function(){fetchPool();};
$('q').oninput=render;
$('btnCopy').onclick=function(){
  var noMail=POOL.filter(function(e){return !e.email;});
  if(!noMail.length){alert('全部已绑定邮箱');return;}
  var txt='请以下成员到登记页绑定通知邮箱（账号异常时邮件通知本人）：\\n'+noMail.map(function(e){return e.name;}).join('\\n');
  function done(){$('btnCopy').textContent='已复制 '+noMail.length+' 条';setTimeout(function(){$('btnCopy').textContent='复制未绑邮箱名单';},2500);}
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(txt).then(done,function(){fallback();});}else fallback();
  function fallback(){var ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done();}catch(e){alert('复制失败，请手动选择');}document.body.removeChild(ta);}
};
$('btnCsv').onclick=function(){
  var rows=[['序号','账号','UID','歌曲ID','入池日期','邮箱','标记']];
  POOL.forEach(function(e,i){rows.push([i+1,e.name,e.uid||'',e.song||'',e.added||'',e.email||'',e.marks||'']);});
  var csv='\ufeff'+rows.map(function(r){return r.map(function(v){return '"'+String(v).replace(/"/g,'""')+'"';}).join(',');}).join('\\r\\n');
  var a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));
  a.download='号池_'+new Date().toISOString().slice(0,10)+'.csv';
  document.body.appendChild(a);a.click();document.body.removeChild(a);
};
function fetchPool(){
  var p='';try{p=localStorage.getItem('poolAdminPass')||'';}catch(e){}
  if(!p){$('loginBox').hidden=false;$('mainBox').hidden=true;return;}
  fetch('/api/pool',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pass:p})})
  .then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});})
  .then(function(o){
    if(!o.ok){msg(o.d.message||'请重新登录');$('loginBox').hidden=false;$('mainBox').hidden=true;return;}
    POOL=o.d.entries||[];STATS=o.d.stats||{};render();
  }).catch(function(){});
}
function badges(e){
  var h='';
  if(e.noListen)h+='<span class="badge b-red">只收</span>';
  if(!e.song)h+='<span class="badge b-gray">公益</span>';
  if(!e.email)h+='<span class="badge b-yellow">无邮箱</span>';
  if(String(e.name).indexOf('qr:')===0)h+='<span class="badge b-gray">扫码</span>';
  return h||'<span style="color:#bbb">正常</span>';
}
function render(){
  var q=($('q').value||'').trim().toLowerCase();
  var list=POOL.filter(function(e){
    if(!q)return true;
    return (e.name+' '+(e.email||'')+' '+(e.uid||'')+' '+(e.song||'')).toLowerCase().indexOf(q)>=0;
  });
  $('stats').innerHTML=
    '<div class="stat"><b>'+STATS.total+'</b><span>号池总数</span></div>'
   +'<div class="stat"><b>'+STATS.withMail+'</b><span>已绑邮箱</span></div>'
   +'<div class="stat'+(STATS.noMail?' warn':'')+'"><b>'+STATS.noMail+'</b><span>未绑邮箱</span></div>'
   +'<div class="stat'+(STATS.noListen?' warn':'')+'"><b>'+STATS.noListen+'</b><span>只收号</span></div>'
   +'<div class="stat"><b>'+STATS.public+'</b><span>公益号</span></div>'
   +'<div class="stat"><b>'+(STATS.limit||500)+'</b><span>人数上限</span></div>'
   +'<div class="stat'+(STATS.remain<=20?' warn':'')+'"><b>'+STATS.remain+'</b><span>剩余名额</span></div>'
   +'<div class="stat"><b>'+(list.length)+'</b><span>当前筛选</span></div>';
  var h='';
  list.forEach(function(e,i){
    var song=e.song?'<a class="song" target="_blank" href="https://music.163.com/song?id='+e.song+'">'+e.song+'</a>':'<span style="color:#bbb">—</span>';
    h+='<tr><td class="num">'+(i+1)+'</td><td>'+esc(e.name)+'</td><td class="num">'+esc(e.uid)+'</td><td class="num">'+song+'</td><td class="num">'+esc(e.added)+'</td><td>'+esc(e.email||'—')+'</td><td>'+badges(e)+'</td></tr>';
  });
  $('tb').innerHTML=h||'<tr><td colspan="7" style="text-align:center;color:#999;padding:20px">没有匹配的账号</td></tr>';
}
try{
  var _pw=null;
  try{var _h=(location.hash||'').match(/(?:^#|[#&])pw=([^&]*)/)||(location.search||'').match(/[?&]pw=([^&]*)/);if(_h)_pw=decodeURIComponent(_h[1]);}catch(e){}
  if(_pw){try{history.replaceState(null,'',location.pathname);}catch(e1){};var _el=$('pw');if(_el)_el.value=_pw;login();}
  else if(localStorage.getItem('poolAdminPass')) fetchPool();
}catch(e){}
</script>
</body>
</html>`;


// 2026-10-25：网页口令输入页（与互助版 worker 同款）。action 留空 = 提交回当前页面。
const GATE_HTML = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>请输入访问口令</title><style>body{font-family:-apple-system,system-ui,"PingFang SC",sans-serif;background:#f5f6f8;margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}.box{background:#fff;border-radius:14px;padding:28px 24px;width:320px;box-shadow:0 2px 12px rgba(0,0,0,.08);text-align:center}h1{font-size:17px;font-weight:600;color:#3b6d11;margin:0 0 6px}p{font-size:13px;color:#666;margin:0 0 18px;line-height:1.6}input{width:100%;box-sizing:border-box;padding:11px;border:1px solid #ddd;border-radius:8px;font-size:15px;text-align:center;letter-spacing:2px}button{margin-top:12px;width:100%;padding:11px;border:0;border-radius:8px;background:#3b6d11;color:#fff;font-size:15px;cursor:pointer}</style></head><body><form class="box" method="get" action=""><h1>成员接入</h1><p>请输入访问口令后继续</p><input name="k" type="password" placeholder="访问口令" autofocus autocomplete="off"><button type="submit">进入</button></form></body></html>`;

// 2026-10-22：D1 绑定只支持 ES Module 格式，故入口从 addEventListener 改为
// export default { fetch }。既有代码全部按 service-worker 时代的「绑定即全局变量」
// 写法（POOL.get / GH_OWNER ...），这里在每个请求开头把 env 挂到 globalThis，
// 一行代码都不用改旧的。绑定对同一 isolate 的所有请求完全相同，挂全局是安全的。
export default {
  async fetch(request, env) {
    globalThis.POOL = env.POOL;
    globalThis.GH_OWNER = env.GH_OWNER;
    globalThis.GH_REPO = env.GH_REPO;
    if (env.DB) globalThis.DB = env.DB;
    try {
      return await handle(request);
    } catch (e) {
      return new Response(JSON.stringify({ message: '服务器内部错误：' + ((e && e.message) || e) }),
        { status: 500, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
    }
  }
};
