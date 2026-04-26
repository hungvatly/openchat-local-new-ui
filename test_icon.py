import struct, zlib

def make_rgba_icon(size, path):
    def png_chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    pixels = []
    bg = (10, 10, 10)
    ac = (200, 194, 184)
    for y in range(size):
        row = bytearray([0]) # filter type 0
        for x in range(size):
            cx, cy = size / 2.0, size / 2.0
            dx, dy = abs(x - cx), abs(y - cy)
            
            # Squircle alpha (radius = 22.5%)
            r_cornerRadius = size * 0.225
            inner_w = size / 2.0 - r_cornerRadius
            dist_x = max(0.0, dx - inner_w)
            dist_y = max(0.0, dy - inner_w)
            dist_from_corner = (dist_x**2 + dist_y**2)**0.5
            
            alpha = 255.0
            if dist_from_corner > r_cornerRadius:
                alpha = max(0.0, 255.0 - (dist_from_corner - r_cornerRadius) * 255.0)
            
            alpha_int = max(0, min(255, int(alpha)))
            
            # Diamond shape with stroke
            r_diamond = size / 3.0
            stroke = size / 12.0
            dist_center = dx + dy
            
            diamond_alpha = 0.0
            if dist_center <= r_diamond and dist_center >= r_diamond - stroke:
                diamond_alpha = 1.0
            elif abs(dist_center - r_diamond) < 1.0:
                diamond_alpha = max(0.0, 1.0 - abs(dist_center - r_diamond))
            elif abs(dist_center - (r_diamond - stroke)) < 1.0:
                diamond_alpha = max(0.0, 1.0 - abs(dist_center - (r_diamond - stroke)))
                
            r = int(ac[0] * diamond_alpha + bg[0] * (1-diamond_alpha))
            g = int(ac[1] * diamond_alpha + bg[1] * (1-diamond_alpha))
            b = int(ac[2] * diamond_alpha + bg[2] * (1-diamond_alpha))
            
            row.extend([r, g, b, alpha_int])
        pixels.append(bytes(row))
        
    raw = b''.join(pixels)
    compressed = zlib.compress(raw, 9)
    ihdr = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0) # 6 = RGBA
    png  = b'\x89PNG\r\n\x1a\n'
    png += png_chunk(b'IHDR', ihdr)
    png += png_chunk(b'IDAT', compressed)
    png += png_chunk(b'IEND', b'')
    with open(path, 'wb') as f: f.write(png)

make_rgba_icon(256, "test_icon.png")
print("Done")
