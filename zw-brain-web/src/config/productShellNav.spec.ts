import { describe, expect, it } from 'vitest';
import { shellNavLabelByKey, shellNavLabelForPath } from './productShellNav';

describe('product shell nav labels', () => {
  it('provider page title comes from the provider nav label', () => {
    expect(shellNavLabelByKey('provider')).toBe('供数据');
    expect(shellNavLabelForPath('/provider')).toBe('供数据');
    expect(shellNavLabelForPath('/provider/inbox/demand-match')).toBe('供数据');
  });
});
