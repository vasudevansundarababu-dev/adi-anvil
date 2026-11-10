// Restricted upstream assertions, never a caller-supplied Promptfoo configuration.
process.env.PROMPTFOO_DISABLE_TELEMETRY = '1';
process.env.PROMPTFOO_DISABLE_UPDATE = '1';
process.env.PROMPTFOO_SAFE_MODE = 'true';

let raw = '';
for await (const chunk of process.stdin) {
  raw += chunk;
  if (Buffer.byteLength(raw) > 65536) throw new Error('Worker input exceeds limit');
}
const value = JSON.parse(raw);
if (value.output === null || value.output === undefined) {
  console.log(JSON.stringify({outcome:'unknown', provider_calls:0}));
} else {
  if (typeof value.output !== 'string' || value.output.length > 8192 ||
      typeof value.expected !== 'string' || value.expected.length > 1000 ||
      value.expected.includes('file://') || /\{[{%]/.test(value.expected) ||
      !['equals', 'contains', 'not-contains'].includes(value.kind)) {
    throw new Error('Unsupported bounded literal assertion');
  }
  const { assertions } = await import('promptfoo');
  const result = await assertions.runAssertion({
    assertion: {type: value.kind, value: value.expected},
    test: {vars:{}}, providerResponse: {output:value.output},
  });
  if (typeof result.pass !== 'boolean') throw new Error('Invalid Promptfoo result');
  console.log(JSON.stringify({outcome:result.pass ? 'pass' : 'fail',
    capability:'deterministic_literal_assertion', provider_calls:0, runtime_version:'0.125.1'}));
}
