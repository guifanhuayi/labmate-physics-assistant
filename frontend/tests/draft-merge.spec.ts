import { describe, expect, it } from 'vitest'
import { mergeValues } from '../src/drafts/merge'

describe('mergeValues', () => {
  it('merges different fields without losing an offline edit', () => {
    expect(mergeValues({ a: '1', b: '2' }, { a: '3', b: '2' }, { a: '1', b: '4' })).toEqual({
      merged: { a: '3', b: '4' }, conflicts: [],
    })
  })
  it('flags the same field changed on both devices', () => {
    expect(mergeValues({ a: '1' }, { a: '2' }, { a: '3' })).toEqual({
      merged: { a: '2' }, conflicts: ['a'],
    })
  })
  it('preserves a deletion and distinguishes it from unchanged', () => {
    expect(mergeValues({ a: '1', b: '2' }, { b: '2' }, { a: '1', b: '3' })).toEqual({
      merged: { b: '3' }, conflicts: [],
    })
  })
})
