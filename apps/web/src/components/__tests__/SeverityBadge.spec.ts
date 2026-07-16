import { mount } from '@vue/test-utils'
import SeverityBadge from '../SeverityBadge.vue'

describe('SeverityBadge', () => {
  it.each([
    ['LOW', '低风险'],
    ['MEDIUM', '中风险'],
    ['HIGH', '高风险'],
    ['CRITICAL', '严重'],
  ] as const)('renders %s with the unified label', (severity, label) => {
    const wrapper = mount(SeverityBadge, { props: { severity } })
    expect(wrapper.text()).toContain(label)
    expect(wrapper.classes()).toContain(`severity-${severity.toLowerCase()}`)
  })
})
