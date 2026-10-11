# -*- coding: utf-8 -*-
import sys
s = open('C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work/pool/pool_page.html', encoding='utf-8').read()
i = s.find('四、持仓变动明细')
j = s.find('五、如何更新最新一季股池')
seg = s[i:j]
print('seg len', len(seg))
# find last </table> in seg
k = seg.rfind('</table>')
print('last </table> at', k)
print('--- tail 3000 ---')
print(seg[k:])
