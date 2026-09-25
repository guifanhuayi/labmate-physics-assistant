import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PhysicsNotationInput from '../src/components/PhysicsNotationInput.vue'
import { renderPhysicsNotation } from '../src/templates/physicsNotation'

describe('physics keyboard notation', () => {
  it('renders editable source notation as structured math without inserting unsafe HTML', () => {
    const html = renderPhysicsNotation('\\bar{x}=\\frac{1}{n}\\sum_{i=1}^{n}x_i + \\Delta x <tag>')
    expect(html).toContain('math-frac')
    expect(html).toContain('<sub>i=1</sub>')
    expect(html).toContain('<sup>n</sup>')
    expect(html).toContain('Δ')
    expect(html).toContain('&lt;tag&gt;')
  })

  it('offers backslash command candidates for keyboard use', async () => {
    const wrapper = mount(PhysicsNotationInput, { props: { label: '测量符号', modelValue: '' } })
    await wrapper.get('input[aria-label="测量符号"]').setValue('\\alp')
    expect(wrapper.get('[aria-label="符号候选"]').text()).toContain('\\alpha')
    await wrapper.get('input[aria-label="测量符号"]').trigger('keydown', { key: 'Tab' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBe('α')
  })
})
