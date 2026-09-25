export interface PhysicsCommand { command: string; output: string; name: string; template?: string; cursor?: number }

export const PHYSICS_COMMANDS: PhysicsCommand[] = [
  ['alpha','α','阿尔法'], ['beta','β','贝塔'], ['gamma','γ','伽马'], ['Gamma','Γ','大写伽马'],
  ['delta','δ','小写德尔塔'], ['Delta','Δ','变化量'], ['epsilon','ϵ','小写 epsilon'], ['varepsilon','ε','另一种 epsilon'],
  ['zeta','ζ','泽塔'], ['eta','η','艾塔'], ['theta','θ','角度'], ['Theta','Θ','大写 theta'],
  ['iota','ι','约塔'], ['kappa','κ','卡帕'], ['lambda','λ','波长'], ['Lambda','Λ','大写 lambda'],
  ['mu','μ','摩擦因数'], ['nu','ν','频率'], ['xi','ξ','克西'], ['Xi','Ξ','大写 xi'],
  ['pi','π','圆周率'], ['Pi','Π','大写 pi'], ['rho','ρ','密度'], ['sigma','σ','标准差'],
  ['Sigma','Σ','求和'], ['tau','τ','转矩'], ['phi','ϕ','相位'], ['varphi','φ','另一种 phi'],
  ['Phi','Φ','磁通量'], ['chi','χ','卡方'], ['psi','ψ','波函数'], ['Psi','Ψ','大写 psi'],
  ['omega','ω','角频率'], ['Omega','Ω','欧姆'], ['pm','±','正负'], ['mp','∓','负正'],
  ['times','×','乘号'], ['cdot','·','点乘'], ['div','÷','除号'], ['approx','≈','约等于'],
  ['neq','≠','不等于'], ['leq','≤','小于等于'], ['geq','≥','大于等于'], ['propto','∝','正比于'],
  ['sim','∼','相似'], ['infty','∞','无穷大'], ['rightarrow','→','向右箭头'],
  ['leftarrow','←','向左箭头'], ['leftrightarrow','↔','双向箭头'], ['partial','∂','偏导'],
  ['nabla','∇','梯度'],
  ['sin','sin','正弦'], ['cos','cos','余弦'], ['tan','tan','正切'], ['ln','ln','自然对数'], ['log','log','对数'],
].map(([command, output, name]) => ({ command: `\\${command}`, output, name }))

PHYSICS_COMMANDS.push(
  { command: '\\frac', output: 'a/b', name: '分式', template: '\\frac{}{}', cursor: 6 },
  { command: '\\sqrt', output: '√x', name: '平方根', template: '\\sqrt{}', cursor: 6 },
  { command: '\\vec', output: 'F⃗', name: '向量箭头', template: '\\vec{}', cursor: 5 },
  { command: '\\bar', output: 'x̄', name: '顶部横线', template: '\\bar{}', cursor: 5 },
  { command: '\\dot', output: 'ẋ', name: '顶部点', template: '\\dot{}', cursor: 5 },
  { command: '\\ddot', output: 'ẍ', name: '顶部双点', template: '\\ddot{}', cursor: 6 },
  { command: '\\hat', output: 'n̂', name: '帽号', template: '\\hat{}', cursor: 5 },
  { command: '\\sum', output: '∑', name: '求和式', template: '\\sum_{}^{}', cursor: 6 },
  { command: '\\int', output: '∫', name: '积分式', template: '\\int_{}^{}', cursor: 6 },
)

const commandMap = new Map(PHYSICS_COMMANDS.map((item) => [item.command.slice(1), item]))
const escapeHtml = (value: string) => value.replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[character] || character)

export function renderPhysicsNotation(value: string): string {
  let index = 0
  function argument(): string {
    if (value[index] === '{') { index += 1; return sequence('}') }
    if (value[index] === '\\') return token()
    if (index >= value.length) return '<span class="math-placeholder">□</span>'
    return escapeHtml(value[index++])
  }
  function token(): string {
    index += 1
    if (value[index] === ',') { index += 1; return '&thinsp;' }
    const start = index
    while (/[A-Za-z]/.test(value[index] || '')) index += 1
    const name = value.slice(start, index)
    if (!name) return '\\'
    if (name === 'frac') return `<span class="math-frac"><span>${argument()}</span><span>${argument()}</span></span>`
    if (name === 'sqrt') {
      let degree = ''
      if (value[index] === '[') {
        index += 1
        const end = value.indexOf(']', index)
        if (end !== -1) { degree = escapeHtml(value.slice(index, end)); index = end + 1 }
      }
      return `<span class="math-root">${degree ? `<sup>${degree}</sup>` : ''}√<span>${argument()}</span></span>`
    }
    if (['vec', 'bar', 'dot', 'ddot', 'hat'].includes(name)) {
      const marks: Record<string, string> = { vec: '→', bar: '¯', dot: '˙', ddot: '¨', hat: 'ˆ' }
      return `<span class="math-accent"><span>${marks[name]}</span>${argument()}</span>`
    }
    const command = commandMap.get(name)
    return command ? escapeHtml(command.output) : escapeHtml(`\\${name}`)
  }
  function sequence(stop?: string): string {
    let result = ''
    while (index < value.length) {
      if (stop && value[index] === stop) { index += 1; break }
      const character = value[index]
      if (character === '\\') result += token()
      else if (character === '_' || character === '^') {
        index += 1
        result += character === '_' ? `<sub>${argument()}</sub>` : `<sup>${argument()}</sup>`
      } else { result += escapeHtml(character); index += 1 }
    }
    return result
  }
  return sequence()
}
