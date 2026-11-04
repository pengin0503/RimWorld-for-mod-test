#version 450
// Both passes sample the same pre-filter scene grab.
layout(location = 0) out vec4 outColor;
layout(set = 2, binding = 0) uniform OgIFParams
{
    float _Temperature;  // @default = 0.0
    float _HueShift;     // @default = 0.0
    float _Saturation;   // @default = 1.0
    float _Contrast;     // @default = 1.0
    float _Brightness;   // @default = 1.0
    float _Gamma;        // @default = 1.0
} u;
layout(set = 2, binding = 1) uniform sampler2D _GrabOgImmersiveFilter;

vec3 RGBToHSV(vec3 c)
{
    vec4 k = vec4(0.0, -1.0/3.0, 2.0/3.0, -1.0);
    vec4 p = mix(vec4(c.bg, k.wz), vec4(c.gb, k.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    return vec3(abs(q.z + (q.w-q.y)/(6.0*d+1.0e-10)), d/(q.x+1.0e-10), q.x);
}
vec3 HSVToRGB(vec3 c)
{
    vec4 k = vec4(1.0, 2.0/3.0, 1.0/3.0, 3.0);
    vec3 p = abs(fract(c.xxx+k.xyz)*6.0-k.www);
    return c.z * mix(k.xxx, clamp(p-k.xxx, 0.0, 1.0), c.y);
}
void main()
{
    ivec2 size = textureSize(_GrabOgImmersiveFilter, 0);
    ivec2 xy = clamp(ivec2(gl_FragCoord.xy), ivec2(0), size-1);
    vec4 col = texelFetch(_GrabOgImmersiveFilter, xy, 0);
    if (abs(u._HueShift) > 0.0001 || abs(u._Saturation - 1.0) > 0.0001)
    {
        vec3 hsv = RGBToHSV(col.rgb);
        hsv.x = fract(hsv.x + u._HueShift);
        hsv.y = clamp(hsv.y * u._Saturation, 0.0, 1.0);
        col.rgb = HSVToRGB(hsv);
    }
    float t = u._Temperature;
    col.rgb *= max(vec3(1.0 + t*0.25, 1.0 + t*0.08, 1.0 - t*0.25), vec3(0.0));
    col.rgb = (col.rgb - 0.5)*u._Contrast + 0.5;
    col.rgb *= u._Brightness;
    col.rgb = pow(max(col.rgb, vec3(0.0)), vec3(1.0/max(u._Gamma, 0.001)));
    outColor = vec4(clamp(col.rgb, 0.0, 1.0), col.a);
}
