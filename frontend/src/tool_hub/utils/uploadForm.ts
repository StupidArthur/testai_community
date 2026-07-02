import type { UploadFile } from 'antd/es/upload/interface'

/** 从 Ant Design Upload fileList 取出原始 File */
export function extractUploadFile(fileList?: UploadFile[]): File | undefined {
  const item = fileList?.[0]
  return item?.originFileObj as File | undefined
}

/** 客户端工具文件必填校验（Form.Item rules） */
export const artifactRequiredRules = [
  {
    validator: async (_: unknown, fileList: UploadFile[]) => {
      if (!fileList?.length) {
        throw new Error('请选择工具文件（exe / zip / msi）')
      }
    },
  },
]

export const artifactUploadFieldProps = {
  valuePropName: 'fileList' as const,
  getValueFromEvent: (e: { fileList?: UploadFile[] } | UploadFile[]) => {
    if (Array.isArray(e)) return e
    return e?.fileList ?? []
  },
}
