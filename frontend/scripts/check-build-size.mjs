import console from 'node:console'
import { readdir, readFile } from 'node:fs/promises'
import process from 'node:process'
import { URL } from 'node:url'
import { gzipSync } from 'node:zlib'
import path from 'node:path'

const ASSETS_DIRECTORY = new URL('../dist/assets/', import.meta.url)
const KIBIBYTE = 1024
const budgets = {
  largestJavaScript: 170 * KIBIBYTE,
  totalJavaScript: 220 * KIBIBYTE,
  totalStyles: 25 * KIBIBYTE,
}

const fileNames = await readdir(ASSETS_DIRECTORY)
const assets = await Promise.all(
  fileNames
    .filter((fileName) => fileName.endsWith('.js') || fileName.endsWith('.css'))
    .map(async (fileName) => {
      const content = await readFile(new URL(fileName, ASSETS_DIRECTORY))
      return {
        fileName,
        gzipBytes: gzipSync(content).byteLength,
        type: path.extname(fileName),
      }
    }),
)

const javaScriptAssets = assets.filter((asset) => asset.type === '.js')
const styleAssets = assets.filter((asset) => asset.type === '.css')
const largestJavaScript = Math.max(...javaScriptAssets.map((asset) => asset.gzipBytes))
const totalJavaScript = sumGzipBytes(javaScriptAssets)
const totalStyles = sumGzipBytes(styleAssets)
const measurements = [
  ['Largest JavaScript asset', largestJavaScript, budgets.largestJavaScript],
  ['Total JavaScript', totalJavaScript, budgets.totalJavaScript],
  ['Total CSS', totalStyles, budgets.totalStyles],
]

for (const [label, actual, budget] of measurements) {
  console.log(`${label}: ${formatKib(actual)} / ${formatKib(budget)} gzip`)
}

const exceeded = measurements.filter(([, actual, budget]) => actual > budget)
if (exceeded.length > 0) {
  console.error('\nBundle size budget exceeded:')
  for (const [label, actual, budget] of exceeded) {
    console.error(`- ${label}: ${formatKib(actual)} > ${formatKib(budget)} gzip`)
  }
  process.exitCode = 1
}

function sumGzipBytes(assetsToSum) {
  return assetsToSum.reduce((total, asset) => total + asset.gzipBytes, 0)
}

function formatKib(bytes) {
  return `${(bytes / KIBIBYTE).toFixed(1)} KiB`
}
