"""Per-file, metadata-guided ProRes profile selection."""
PROFILES={'proxy':('422 Proxy',0,45),'lt':('422 LT',1,102),'standard':('422',2,147),'hq':('422 HQ',3,220),'4444':('4444',4,330),'4444xq':('4444 XQ',5,500)}
FORMATS={'yuv420p':(8,'420',False),'yuvj420p':(8,'420',False),'yuv422p':(8,'422',False),'yuvj422p':(8,'422',False),'yuv420p10le':(10,'420',False),'yuv422p10le':(10,'422',False),'yuv444p':(8,'444',False),'yuvj444p':(8,'444',False),'yuv444p10le':(10,'444',False),'yuva420p':(8,'420',True),'yuva422p':(8,'422',True),'yuva444p':(8,'444',True),'yuva444p10le':(10,'444',True),'gbrp':(8,'rgb',False),'gbrp10le':(10,'rgb',False),'gbrap':(8,'rgb',True),'gbrap10le':(10,'rgb',True),'rgb24':(8,'rgb',False),'bgr24':(8,'rgb',False),'rgba':(8,'rgb',True),'bgra':(8,'rgb',True),'argb':(8,'rgb',True),'abgr':(8,'rgb',True)}

FORMATS.update({name:(8,'rgb',False) for name in ['bgr0','rgb0','0bgr','0rgb']})

def resolve(item,settings):
    if any(not item.get(k) or item[k]<=0 for k in ['width','height','fps','duration']):raise ValueError('ProRes needs known dimensions, duration and frame rate')
    pixel=item.get('pixel_format','')
    if item.get('color_transfer') in ('smpte2084','arib-std-b67'):raise ValueError('HDR ProRes conversion is not supported yet; keep this source unchanged')
    if pixel not in FORMATS:raise ValueError('ProRes supports known 8/10-bit SDR sources; 12-bit, RAW and unknown formats are not supported')
    bits,chroma,alpha=FORMATS[pixel]
    requested=settings.get('proresProfile','auto')
    if requested not in ('auto',*PROFILES):raise ValueError('Choose a valid ProRes profile')
    chosen=('4444' if alpha or chroma in ('444','rgb') else 'hq' if bits==10 or settings.get('proresPreferFidelity') is True else 'standard') if requested=='auto' else requested
    if alpha and chosen not in ('4444','4444xq'):raise ValueError('This file has alpha; choose Automatic, 4444 or 4444 XQ to retain it')
    label,number,rate=PROFILES[chosen]
    full=number>=4
    output='yuva444p10le' if full and alpha else 'yuv444p10le' if full else 'yuv422p10le'
    reason='Retains transparency and full chroma' if alpha else 'Retains full chroma sampling' if chroma in ('444','rgb') and full else 'Higher fidelity preference' if requested=='auto' and settings.get('proresPreferFidelity') is True else '10-bit source' if bits==10 else 'Balanced profile for 8-bit footage'
    if requested!='auto':reason='Selected manually'+(' · Converts full chroma to 4:2:2' if chroma in ('444','rgb') and not full else '')
    if chroma=='rgb':reason+=' · RGB converts to 10-bit YUV'
    estimate=rate*1e6/8*(item['width']*item['height']/(1920*1080))*(item['fps']/29.97)*item['duration']
    return {'profile':chosen,'profileNumber':number,'label':'ProRes '+label,'pixelFormat':output,'alpha':alpha,'rgb':chroma=='rgb','reason':reason,'estimatedVideoBytes':estimate}
