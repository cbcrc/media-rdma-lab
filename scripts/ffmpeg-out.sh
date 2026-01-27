dd if=/dev/shm/mxl/3567954b-8ac2-2bf8-6a03-7cac463d511f.mxl-flow/grains/data.1  skip=8192 ibs=1  |  \
docker run --rm -i -v $(pwd):/config linuxserver/ffmpeg \
-f rawvideo -pix_fmt yuv422p10le -s 1920x1080 -c:v v210 -i pipe:0 /config/out.png