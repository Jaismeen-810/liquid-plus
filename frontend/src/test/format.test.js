import { money, pct, gapClass } from '../format'

test('money uses compact units and a real minus sign', () => {
  expect(money(437_100_000)).toBe('437.1M')
  expect(money(-3_111_900_000)).toBe('−3.11B')
  expect(money(-52_000)).toBe('−52K')
  expect(money(0)).toBe('0')
  expect(money(null)).toBe('–')
})

test('pct and gap colouring', () => {
  expect(pct(0.73525)).toBe('73.5%')
  expect(pct(undefined)).toBe('–')
  expect(gapClass(-1)).toBe('neg')
  expect(gapClass(5)).toBe('pos')
  expect(gapClass(0)).toBe('')
})
