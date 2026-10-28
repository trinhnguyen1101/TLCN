// Load the real source modules with TypeScript's existing compiler. Node's native
// TS stripping does not resolve the application's extensionless bundler imports.
import {readFileSync} from 'node:fs'
import ts from 'typescript'
export function sourceModule(url) {
  let source=ts.transpileModule(readFileSync(url,'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
  source=source.replace(/from (['"])(\.[^'"]+)\1/g,(_,quote,dependency)=>`from ${quote}${sourceModule(new URL(`${dependency}.ts`,url))}${quote}`)
  return `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
}
