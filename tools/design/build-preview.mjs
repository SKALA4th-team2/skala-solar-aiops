import {readFile,writeFile} from 'node:fs/promises';
const folder=new URL('../../docs/design/solar-ops-v01/',import.meta.url);
const [html,css,refinements,js]=await Promise.all(['index.html','styles.css','refinements.css','hourly-ui.js'].map(f=>readFile(new URL(f,folder),'utf8')));
const font=await readFile(new URL("PretendardVariable.woff2",folder));
const bundledCss=css.replace('url("PretendardVariable.woff2")',`url("data:font/woff2;base64,${font.toString("base64")}")`);
const output=html.replace('<link rel="stylesheet" href="styles.css">',()=>`<style>${bundledCss}</style>`).replace('<link rel="stylesheet" href="refinements.css">',()=>`<style>${refinements}</style>`).replace('  <script src="hourly-ui.js" defer></script>','').replace('</body>',()=>`<script>${js}</script></body>`);
await writeFile(new URL('solar-ops-preview.html',folder),output,'utf8');
console.log('Built hourly Solar Ops preview');
