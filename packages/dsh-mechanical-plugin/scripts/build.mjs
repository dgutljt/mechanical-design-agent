import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { stripTypeScriptTypes } from 'node:module';

for (const file of ['index', 'bridge/python', 'contracts/torque', 'contracts/shaft-workflow']) {
  const source = join(import.meta.dirname, '..', 'src', `${file}.ts`);
  const destination = join(import.meta.dirname, '..', 'dist', `${file}.js`);
  await mkdir(join(destination, '..'), { recursive: true });
  await writeFile(destination, stripTypeScriptTypes(await readFile(source, 'utf8')));
}
