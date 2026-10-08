import {readFile,writeFile} from 'node:fs/promises';
const folder=new URL('../../docs/design/solar-ops-v01/',import.meta.url);
const [html,css,js]=await Promise.all(['index.html','styles.css','hourly-ui.js'].map(f=>readFile(new URL(f,folder),'utf8')));
const output=html.replace('<link rel="stylesheet" href="styles.css">',()=>`<style>${css}</style>`).replace('  <script src="hourly-ui.js" defer></script>','').replace('</body>',()=>`<script>${js}</script></body>`);
await writeFile(new URL('solar-ops-preview.html',folder),output,'utf8');
console.log('Built hourly Solar Ops preview');
