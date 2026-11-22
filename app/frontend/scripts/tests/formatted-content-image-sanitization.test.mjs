import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

function loadFormattedContentModule() {
  const source = readFileSync(new URL('../../src/components/FormattedContent.tsx', import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { 
      module: ts.ModuleKind.CommonJS, 
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX
    },
  });

  const Fragment = Symbol('Fragment');
  const makeNode = (type, props) => ({ type, props });

  const exports = {};
  runInNewContext(outputText, {
    exports,
    require: (id) => {
      if (id === 'react' || id === 'react/jsx-runtime') {
        const reactApi = {
          createElement: (type, props, ...children) => makeNode(type, { ...props, children }),
          useMemo: (fn) => fn(),
          useState: (init) => [init, () => {}],
          jsx: (type, props) => makeNode(type, props),
          jsxs: (type, props) => makeNode(type, props),
          Fragment
        };
        return { __esModule: true, default: reactApi, ...reactApi };
      }
      if (id === 'lucide-react') {
        return new Proxy({}, { get: () => () => null });
      }
      return {};
    },
    console: { log() {}, warn() {}, error() {} },
    Error: globalThis.Error,
    TypeError: globalThis.TypeError,
    Math: globalThis.Math,
    Boolean: globalThis.Boolean,
    encodeURI: globalThis.encodeURI,
    decodeURI: globalThis.decodeURI,
    Array: globalThis.Array,
    Set: globalThis.Set,
    String: globalThis.String,
    RegExp: globalThis.RegExp
  });

  return { ...exports, Fragment };
}

function serializeTree(node, FragmentSym) {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map((n) => serializeTree(n, FragmentSym)).join('');
  if (typeof node === 'object') {
    const inner = serializeTree(node.props?.children, FragmentSym);
    if (node.type === FragmentSym || typeof node.type !== 'string') return inner;
    if (node.type === 'br' || node.type === 'hr') return `<${node.type}/>`;
    return `<${node.type}>${inner}</${node.type}>`;
  }
  return '';
}

test('preprocessMarkdown: sanitiza URLs de imagens com espaços e parênteses sem quebrar tags', () => {
  const { preprocessMarkdown } = loadFormattedContentModule();

  const input = `
Diagnóstico: 3 critérios maiores MAIS 1 critério menor.
![imagem](https://cdn.medway.com.br/media/question_explanation_images/Sem título-1 (1).png)

Tratamento: Ambulatorial vs Hospitalar
![imagem](https://cdn.medway.com.br/media/question_explanation_images/Sem título-12 (1).png)
`;

  const output = preprocessMarkdown(input);

  // Não deve conter parênteses brutos não-escapados dentro da URL antes do fechamento
  assert.ok(output.includes('Sem%20t%C3%ADtulo-1%20%281%29.png'));
  assert.ok(output.includes('Sem%20t%C3%ADtulo-12%20%281%29.png'));
  assert.ok(!output.includes('Sem título-1 (1).png'));
});

test('normalizeImageSrc: sanitiza URLs com espaços e caracteres especiais', () => {
  const { normalizeImageSrc } = loadFormattedContentModule();

  const rawUrl = 'https://cdn.medway.com.br/media/question_explanation_images/HAS (MAPA).png';
  const normalized = normalizeImageSrc(rawUrl);

  assert.equal(normalized, 'https://cdn.medway.com.br/media/question_explanation_images/HAS%20%28MAPA%29.png');
});

test('preprocessMarkdown: limpa NBSP, bold vazio (** **) e espaços órfãos antes de pontuação sem corromper URLs', () => {
  const { preprocessMarkdown } = loadFormattedContentModule();

  const input = `Trata-se de flutter atrial , logo com aspecto de dentes de serra .\n\n**\u00A0**\n\nO intervalo é regular ou irregular ?\n![img](https://cdn.medway.com.br/media/a , b.png)`;
  const out = preprocessMarkdown(input);

  assert.ok(out.includes('flutter atrial, logo com aspecto de dentes de serra.'));
  assert.ok(out.includes('irregular?'));
  assert.ok(!out.includes('** **'));
  assert.ok(!out.includes('\u00A0'));
  assert.ok(out.includes('https://cdn.medway.com.br/media/a%20,%20b.png'));
});

test('FormattedContent: renderiza *itálico*, ***negrito+itálico***, LaTeX clínico e preserva R$ e multiplicação', () => {
  const { FormattedContent, Fragment } = loadFormattedContentModule();

  const md = [
    'Achado de *pseudohifas* e ***ISRS* são primeira escolha**.',
    '***Também pode cair:** paracentese diagnóstica*',
    'Gasometria: $pH$: 7,28; $PaCO_2$: 55; $HCO_3^-$: 24; Glasgow $\\le$ 8.',
    'Cálculo: (50*100)/(1.000) e gasto de R$ 711,4 bilhões versus R$ 427,8 bilhões.'
  ].join('\n\n');

  const html = serializeTree(FormattedContent({ content: md }), Fragment);

  assert.ok(html.includes('<em>pseudohifas</em>'), `Deveria renderizar itálico: ${html}`);
  assert.ok(html.includes('<strong><em>ISRS</em> são primeira escolha</strong>'), `Deveria renderizar itálico dentro de bold: ${html}`);
  assert.ok(html.includes('<em><strong>Também pode cair:</strong> paracentese diagnóstica</em>'), `Deveria renderizar bold dentro de itálico: ${html}`);
  assert.ok(html.includes('PaCO<sub>2</sub>'), `Deveria renderizar subscrito LaTeX: ${html}`);
  assert.ok(html.includes('HCO<sub>3</sub><sup>-</sup>'), `Deveria renderizar sub+sup LaTeX: ${html}`);
  assert.ok(html.includes('≤'), `Deveria converter \\le em ≤: ${html}`);
  assert.ok(html.includes('(50*100)/(1.000)'), `Multiplicação não pode virar itálico: ${html}`);
  assert.ok(html.includes('R$ 711,4 bilhões versus R$ 427,8 bilhões'), `Valores em R$ não podem virar math: ${html}`);
});

test('FormattedContent: converte blocos de pistas-chave e pares **Chave:** valor sem marcador em lista legível e preserva quebras de linha', () => {
  const { FormattedContent, Fragment } = loadFormattedContentModule();

  const md = [
    '**Pistas-chave:**',
    '',
    'Plaquetopenia',
    'Esquistossomose hepatoesplênica',
    '',
    'Características do Estudo Transversal',
    '**Temporalidade:** exposição e desfecho simultâneos',
    '**Limitação:** causalidade reversa'
  ].join('\n');

  const html = serializeTree(FormattedContent({ content: md }), Fragment);

  assert.ok(html.includes('<h4>Pistas-chave:</h4><ul><li>Plaquetopenia</li><li>Esquistossomose hepatoesplênica</li></ul>'), html);
  assert.ok(html.includes('<h4>Características do Estudo Transversal</h4><ul><li><strong>Temporalidade:</strong> exposição e desfecho simultâneos</li><li><strong>Limitação:</strong> causalidade reversa</li></ul>'), html);
});
