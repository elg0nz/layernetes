// Ambient WebGL background field. Ported from the Claude Design mockups'
// DCLogic canvas shader (React) to a plain DOM/WebGL2 module — same GLSL,
// same warm color bias, same reduced-motion behavior.
const VS = '#version 300 es\nin vec2 aPos;\nvoid main(){ gl_Position = vec4(aPos, 0., 1.); }';
const FS = [
  '#version 300 es',
  'precision highp float;',
  'uniform vec3 iResolution;',
  'uniform float iTime;',
  'out vec4 fragColor;',
  'void mainImage(out vec4 O, vec2 C){',
  '  O-=O;',
  '  vec3 R = iResolution,',
  '       p = 4./R,',
  '       A = vec3(0,.6,.8),',
  '       q = R-R;',
  '  for( float i=0.,s; i++<3e2; )',
  '    q = int(i)%3 > 1 ?',
  '          s = length(--q.xz)*.5 - .04,',
  '          O += .9/exp(s*vec4(1,2,4,1))/i,',
  '          abs( mix(A*dot(p -= normalize(vec3(C+C,R)-R) * s,A),',
  '                   p, cos(s=iTime))+sin(s)*cross(p,A) )',
  '      :',
  '          q.x<q.y ? q.zxy : q.zyx;',
  '  O *= O;',
  '}',
  'void main(){',
  '  vec4 O;',
  '  mainImage(O, gl_FragCoord.xy);',
  '  O.rgb *= vec3(1.0, 0.72, 0.42);',
  '  fragColor = vec4(O.rgb, 1.0);',
  '}',
].join('\n');

function compile(gl, type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    console.warn('shader compile:', gl.getShaderInfoLog(sh));
    return null;
  }
  return sh;
}

export function initShaderBackground(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const gl = canvas.getContext('webgl2', {
    antialias: false,
    alpha: true,
    premultipliedAlpha: false,
    preserveDrawingBuffer: true,
  });
  if (!gl) {
    canvas.style.display = 'none';
    return;
  }

  const vs = compile(gl, gl.VERTEX_SHADER, VS);
  const fs = compile(gl, gl.FRAGMENT_SHADER, FS);
  if (!vs || !fs) {
    canvas.style.display = 'none';
    return;
  }

  const prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.bindAttribLocation(prog, 0, 'aPos');
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    console.warn('shader link:', gl.getProgramInfoLog(prog));
    canvas.style.display = 'none';
    return;
  }
  gl.useProgram(prog);

  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

  const uRes = gl.getUniformLocation(prog, 'iResolution');
  const uTime = gl.getUniformLocation(prog, 'iTime');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  const resize = () => {
    const maxW = 760;
    const vw = window.innerWidth || 1200;
    const vh = window.innerHeight || 800;
    const scale = Math.min(1, maxW / vw);
    canvas.width = Math.max(2, Math.round(vw * scale));
    canvas.height = Math.max(2, Math.round(vh * scale));
    gl.viewport(0, 0, canvas.width, canvas.height);
  };
  resize();
  window.addEventListener('resize', resize);

  const t0 = performance.now();
  const draw = (now) => {
    const t = reduce ? 5.4 : ((now - t0) / 1000) * 0.26;
    gl.uniform3f(uRes, canvas.width, canvas.height, 1.0);
    gl.uniform1f(uTime, t);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };

  draw(performance.now());
  if (!reduce) {
    setInterval(() => draw(performance.now()), 33);
  }
}
