# 《Limen》Blender 工程

本项目提供《Limen》分步测试中使用的三个 Blender 场景工程，包含泳池馆与后室场景。

## 下载与说明

- [下载 Blender 工程包](Limen_Blender工程.zip)
- [从 GitHub Release 下载](https://github.com/novahanser/ai-motion-creation/releases/download/limen-blender-project/Limen_Blender_project.zip)
- [查看工程包原始说明](说明.txt)

两个压缩包下载入口的内容相同。包内有三个 `.blend` 文件及一份说明：

| 工程 | 内容 |
| --- | --- |
| `泳池馆_第4步.blend` | 泳池馆场景，包含 11 个机位。 |
| `泳池馆_40秒_第4步.blend` | 扩展后的泳池馆场景，包含 21 个机位。 |
| `后室_第4步.blend` | 后室及侧间场景，包含 5 个机位。 |

## 使用说明

- 工程使用 Blender 5.2 保存，建议使用 Blender 5.2 或更新版本打开。
- 场景贴图已打包进各自的 `.blend` 文件。如需单独编辑贴图，可在 Blender 中选择「文件 → 外部数据 → 解包资源」。
- 工程保存的渲染设置为 Cycles、1920 × 1080、30 fps、384 采样。实际渲染时可按需要调整。
- 包内未包含逐帧控制水位、灯光、机位等变化的 Python 脚本，也没有这些变化对应的动画关键帧。打开工程时看到的是保存时的静态状态。
- 动态分镜中的合成调色、颗粒、屏幕文字和线条不包含在 Blender 工程内。

原交付记录注明，部分已嵌入的文字贴图使用了 `ヒラギノ丸ゴ Pro W4` 字体，其授权状态尚未确认。
