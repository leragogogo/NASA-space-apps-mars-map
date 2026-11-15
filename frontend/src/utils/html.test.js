import { expect, test } from 'vitest'
import { escapeHtml } from './html.js'

test('escapes the five HTML special characters', () => {
  expect(escapeHtml(`<a href="x">&'</a>`)).toBe('&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;')
})

test('turns null and undefined into an empty string', () => {
  expect(escapeHtml(null)).toBe('')
  expect(escapeHtml(undefined)).toBe('')
})

test('stringifies numbers', () => {
  expect(escapeHtml(42)).toBe('42')
})
