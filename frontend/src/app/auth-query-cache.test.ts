import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

describe("canonical auth query-cache isolation", () => {
  const source = readFileSync(join(process.cwd(), "src/app/auth.tsx"), "utf8")

  it("clears TanStack Query cache when canonical logout completes", () => {
    const logoutBlock = source.match(/const logout = async \(\) => \{([\s\S]*?)\n {2}\}/)?.[1] ?? ""
    expect(logoutBlock).toContain("queryClient.clear()")
    expect(logoutBlock.indexOf("queryClient.clear()")).toBeLessThan(logoutBlock.indexOf("setSession(null)"))
  })

  it("clears cached project data on authentication failure events", () => {
    const effectBlock = source.slice(source.indexOf("useEffect(() =>"))
    const expiredLine = effectBlock.split("\n").find((line) => line.includes("const expired =")) ?? ""
    expect(expiredLine).toContain("queryClient.clear()")
    expect(expiredLine.indexOf("queryClient.clear()")).toBeLessThan(expiredLine.indexOf("setSession(null)"))
  })
})
