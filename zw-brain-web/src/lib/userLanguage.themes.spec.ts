import { describe, it, expect } from 'vitest';
import {
  displayRecordName,
  looksLikeBareCode,
  isTestMarkerName,
  stripKindSuffix,
} from './userLanguage';

// Locks the Theme 1/2/3 R12 display helpers against real defect values found in
// the live audit (so they cannot silently regress to leaking raw codes / junk).
describe('displayRecordName (Theme 1: never show raw id/code as a name)', () => {
  it('returns a real business name unchanged', () => {
    expect(displayRecordName('农村集体经济组织登记证', '0f5e8b666bdd4335b69f4330245e78e6', '交付任务')).toBe(
      '农村集体经济组织登记证',
    );
    expect(displayRecordName('人口基础信息主目录', '11370000MB284651XL2001', '目录')).toBe('人口基础信息主目录');
  });
  it('demotes name == org-code to 未命名（编码 …末6位）', () => {
    const code = '11370000MB284651XL2001610030503001';
    expect(displayRecordName(code, code, '目录')).toBe('未命名目录（编码 …503001）');
  });
  it('demotes a bare 32-hex id title', () => {
    const id = '46f0c75eb0c14ee4ba571a292e96194f';
    expect(displayRecordName(id, id, '授权')).toBe('未命名授权（编码 …96194f）');
  });
  it('falls back when name is empty', () => {
    expect(displayRecordName('', '11370000MB284651XL2001610030503001', '目录')).toBe('未命名目录（编码 …503001）');
  });
});

describe('looksLikeBareCode (catches org-codes isBareHexId misses)', () => {
  it('flags org credit code + serial', () => {
    expect(looksLikeBareCode('11370000MB284651XL2001610030503001')).toBe(true);
  });
  it('flags 32-hex', () => {
    expect(looksLikeBareCode('46f0c75eb0c14ee4ba571a292e96194f')).toBe(true);
  });
  it('does NOT flag a real Chinese name', () => {
    expect(looksLikeBareCode('历年GDP信息')).toBe(false);
  });
});

describe('isTestMarkerName (Theme 3: conservative junk filter — 宁漏勿误)', () => {
  it('filters obvious test/junk rows', () => {
    for (const n of ['测试资源-5', '复测sxl服务', '测试28', '11111', 'dhdhdjjjjjjjjjj']) {
      expect(isTestMarkerName(n), n).toBe(true);
    }
  });
  it('keeps real gov data names (no false positives)', () => {
    for (const n of ['历年GDP信息', '重大危险源基本信息', '中小学生信息', '融合服务测试-1']) {
      expect(isTestMarkerName(n), n).toBe(false);
    }
  });
});

describe('stripKindSuffix (Theme 3: drop engineering name suffix)', () => {
  it('strips _库表资源 / _文件资源', () => {
    expect(stripKindSuffix('重大危险源基本信息_库表资源')).toBe('重大危险源基本信息');
    expect(stripKindSuffix('重大危险源基本信息_文件资源')).toBe('重大危险源基本信息');
  });
  it('leaves a clean name unchanged', () => {
    expect(stripKindSuffix('历年GDP信息')).toBe('历年GDP信息');
  });
});
