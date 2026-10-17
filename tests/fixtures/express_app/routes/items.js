// 合成 fixture：一个最小的 Express 路由文件，用于验证 Node 分析器。
const express = require('express')
const router = express.Router()

router.get('/items', (req, res) => {
  res.json([])
})

router.post('/items', (req, res) => {
  res.json({ ok: true })
})

router.delete('/items/:id', (req, res) => {
  res.json({ ok: true })
})

module.exports = router
