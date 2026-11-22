import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function loadTsModule(filePath, extraMocks = {}) {
  const source = fs.readFileSync(filePath, 'utf8');
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.React,
      esModuleInterop: true,
    },
    fileName: filePath,
  }).outputText;

  const mod = { exports: {} };
  const sandbox = {
    module: mod,
    exports: mod.exports,
    require: (id) => {
      if (id in extraMocks) return extraMocks[id];
      if (id === 'react') return React;
      if (id === 'lucide-react') return { Maximize: () => null };
      return require(id);
    },
    console,
  };
  vm.runInNewContext(transpiled, sandbox, { filename: filePath });
  return mod.exports;
}

const textHighlightsPath = path.resolve(process.cwd(), 'src/lib/textHighlights.ts');
const formattedContentPath = path.resolve(process.cwd(), 'src/components/FormattedContent.tsx');

const textHighlightsMod = loadTsModule(textHighlightsPath);
const formattedContentMod = loadTsModule(formattedContentPath, {
  '@/lib/textHighlights': textHighlightsMod,
});

const { addOrMergeHighlight } = textHighlightsMod;
const { FormattedContent } = formattedContentMod;

test('addOrMergeHighlight: insere ordenado, funde mesma cor e recorta cor diferente', () => {
  const summarize = (arr) => Array.from(arr, (h) => [h.start, h.end, h.color]);
  let list = [];
  list = addOrMergeHighlight(list, { id: 'a', start: 20, end: 30, color: 'yellow' });
  list = addOrMergeHighlight(list, { id: 'b', start: 5, end: 12, color: 'yellow' });
  assert.deepEqual(summarize(list), [
    [5, 12, 'yellow'],
    [20, 30, 'yellow'],
  ]);

  // Sobreposição da mesma cor funde
  list = addOrMergeHighlight(list, { id: 'c', start: 10, end: 22, color: 'yellow' });
  assert.deepEqual(summarize(list), [[5, 30, 'yellow']]);

  // Sobreposição de cor diferente recorta o grifo anterior
  list = addOrMergeHighlight(list, { id: 'd', start: 12, end: 18, color: 'green' });
  assert.deepEqual(summarize(list), [
    [5, 12, 'yellow'],
    [12, 18, 'green'],
    [18, 30, 'yellow'],
  ]);
});

test('FormattedContent: aplica <mark> por offset inclusive cruzando negrito e preservando ocorrências repetidas', () => {
  const text = 'Paciente com **dor torácica** e dor abdominal.';
  // Texto renderizado sem markdown: "Paciente com dor torácica e dor abdominal."
  //                                  012345678901234567890123456789012345678901
  // "com dor" => start 9, end 16 (cruza texto plano + <strong>)
  const html = renderToStaticMarkup(
    React.createElement(FormattedContent, {
      content: text,
      highlights: [{ id: 'hl-1', start: 9, end: 16, color: 'yellow' }],
      onRemoveHighlight: () => {},
    })
  );

  assert.match(html, /<mark data-highlight-id="hl-1"[^>]*>com <\/mark>/);
  assert.match(html, /<strong[^>]*><mark data-highlight-id="hl-1"[^>]*>dor<\/mark> torácica<\/strong>/);
  // A segunda ocorrência de "dor" não foi grifada
  assert.match(html, / e dor abdominal\./);
});
