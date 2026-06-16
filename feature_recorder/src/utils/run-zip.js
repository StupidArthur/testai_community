/**
 * run-zip.js - 将单次录制 run_* 目录打包为 zip（供 AI 翻译上传）
 *
 * 输出位置：与 run 目录同级，例如 output/run_2026-06-16T12-00-00.zip
 * zip 内保留 run_* 文件夹结构，平台 safe_extract 可识别 meta.json。
 */

import { execFile } from 'child_process';
import fs from 'fs';
import path from 'path';
import { promisify } from 'util';

import { META_FILENAME } from './config.js';

const execFileAsync = promisify(execFile);

/** ZIP 打包超时（大录制包可能较慢） */
const ZIP_TIMEOUT_MS = 5 * 60 * 1000;

/**
 * 计算 run 目录对应的 zip 路径
 *
 * @param {string} runDir - run_* 绝对路径
 * @returns {string}
 */
export function getRunZipPath(runDir) {
  const runId = path.basename(runDir);
  return path.join(path.dirname(runDir), `${runId}.zip`);
}

/**
 * 判断 run 是否已有 zip
 *
 * @param {string} runDir
 * @returns {boolean}
 */
export function runZipExists(runDir) {
  return fs.existsSync(getRunZipPath(runDir));
}

/**
 * 将 run_* 目录打包为 zip
 *
 * @param {string} runDir - run_* 绝对路径
 * @returns {Promise<string>} zip 绝对路径
 */
export async function zipRunDirectory(runDir) {
  const metaPath = path.join(runDir, META_FILENAME);
  if (!fs.existsSync(metaPath)) {
    throw new Error(`meta.json 不存在，无法打包: ${runDir}`);
  }

  const zipPath = getRunZipPath(runDir);
  if (fs.existsSync(zipPath)) {
    fs.unlinkSync(zipPath);
  }

  if (process.platform === 'win32') {
    const ps = [
      '$ErrorActionPreference = "Stop"',
      `$src = '${runDir.replace(/'/g, "''")}'`,
      `$dst = '${zipPath.replace(/'/g, "''")}'`,
      'if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Force }',
      'Compress-Archive -LiteralPath $src -DestinationPath $dst -CompressionLevel Optimal',
    ].join('; ');
    await execFileAsync(
      'powershell.exe',
      ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
      { timeout: ZIP_TIMEOUT_MS },
    );
  } else {
    const parent = path.dirname(runDir);
    const runId = path.basename(runDir);
    await execFileAsync('zip', ['-r', zipPath, runId], { cwd: parent, timeout: ZIP_TIMEOUT_MS });
  }

  if (!fs.existsSync(zipPath)) {
    throw new Error(`ZIP 创建失败: ${zipPath}`);
  }
  return zipPath;
}

/**
 * 等待 meta.json 落盘后打包（浏览器关闭触发收尾时可能略有延迟）
 *
 * @param {string} runDir
 * @param {{ info?: (msg: string) => void, warn?: (msg: string) => void }} [logger]
 * @returns {Promise<string|null>} zip 路径；失败返回 null
 */
export async function zipRunDirectoryWhenReady(runDir, logger = {}) {
  const metaPath = path.join(runDir, META_FILENAME);
  for (let i = 0; i < 12; i++) {
    if (fs.existsSync(metaPath)) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (!fs.existsSync(metaPath)) {
    logger.warn?.('meta.json 未生成，跳过 ZIP 打包');
    return null;
  }
  try {
    const zipPath = await zipRunDirectory(runDir);
    logger.info?.(`已生成 ZIP: ${path.basename(zipPath)}（可上传到 AI 翻译）`);
    return zipPath;
  } catch (error) {
    logger.warn?.(`ZIP 打包失败: ${error.message}`);
    return null;
  }
}
