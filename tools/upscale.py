"""4x AI upscaler for contributed wallpapers, with no PyTorch needed.

Runs Real-ESRGAN's compact general model (realesr-general-x4v3, BSD-3-Clause, by Xintao Wang et al.)
through onnxruntime. The .pth weights are read straight from the zip without torch.

    pip install numpy pillow onnx onnxruntime
    curl -LO https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth
    python3 tools/upscale.py realesr-general-x4v3.pth in.png out.png
"""
import io, pickle, sys, zipfile
import numpy as np
from PIL import Image


def load_pth(path):
    """Minimal reader for torch's zip checkpoint format: returns {name: float32 ndarray}."""
    z = zipfile.ZipFile(path)
    root = z.namelist()[0].split("/")[0]

    class Storage:
        def __init__(self, key):
            self.a = np.frombuffer(z.read(f"{root}/data/{key}"), np.float32)

    def rebuild(storage, offset, size, stride, *_):
        a = storage.a
        return np.lib.stride_tricks.as_strided(a[offset:], size, [s * 4 for s in stride]).copy() if size else a[offset:offset + 1].copy()

    class U(pickle.Unpickler):
        def find_class(self, mod, name):
            if name == "_rebuild_tensor_v2":
                return rebuild
            if name == "FloatStorage":
                return "float"
            if mod == "collections" and name == "OrderedDict":
                import collections
                return collections.OrderedDict
            raise pickle.UnpicklingError(f"unexpected {mod}.{name}")  # nothing else may load

        def persistent_load(self, pid):
            _, dtype, key, *_ = pid
            assert dtype == "float", dtype
            return Storage(key)

    d = U(io.BytesIO(z.read(f"{root}/data.pkl"))).load()
    return d.get("params_ema") or d.get("params") or d


def build_onnx(sd, path):
    """SRVGGNetCompact: conv+PReLU, 32x (conv+PReLU), conv to 48ch, pixel-shuffle x4, plus nearest-upsampled input."""
    from onnx import helper, TensorProto, numpy_helper, save
    inits, nodes, x = [], [], "input"
    idx = sorted({int(k.split(".")[1]) for k in sd})
    for i in idx:
        w = sd[f"body.{i}.weight"]
        if w.ndim == 4:
            inits += [numpy_helper.from_array(w, f"w{i}"), numpy_helper.from_array(sd[f"body.{i}.bias"], f"b{i}")]
            nodes.append(helper.make_node("Conv", [x, f"w{i}", f"b{i}"], [f"y{i}"], pads=[1, 1, 1, 1]))
        else:
            inits.append(numpy_helper.from_array(w.reshape(-1, 1, 1), f"a{i}"))
            nodes.append(helper.make_node("PRelu", [x, f"a{i}"], [f"y{i}"]))
        x = f"y{i}"
    nodes.append(helper.make_node("DepthToSpace", [x], ["sh"], blocksize=4, mode="CRD"))
    inits.append(numpy_helper.from_array(np.array([1, 1, 4, 4], np.float32), "scales"))
    nodes.append(helper.make_node("Resize", ["input", "", "scales"], ["up"], mode="nearest"))
    nodes.append(helper.make_node("Add", ["sh", "up"], ["output"]))
    g = helper.make_graph(nodes, "srvgg", [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, None, None])],
                          [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 3, None, None])], inits)
    save(helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)], ir_version=8), path)


def upscale(sess, img, tile=256, pad=12):
    a = np.asarray(img.convert("RGB"), np.float32).transpose(2, 0, 1)[None] / 255
    _, _, h, w = a.shape
    out = np.zeros((1, 3, h * 4, w * 4), np.float32)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            y0, x0, y1, x1 = max(0, y - pad), max(0, x - pad), min(h, y + tile + pad), min(w, x + tile + pad)
            r = sess.run(None, {"input": a[:, :, y0:y1, x0:x1]})[0]
            ty, tx = min(tile, h - y), min(tile, w - x)  # keep only the tile's core, drop the padded seams
            out[:, :, y * 4:(y + ty) * 4, x * 4:(x + tx) * 4] = r[:, :, (y - y0) * 4:(y - y0 + ty) * 4, (x - x0) * 4:(x - x0 + tx) * 4]
    return Image.fromarray((np.clip(out[0].transpose(1, 2, 0), 0, 1) * 255 + 0.5).astype(np.uint8))


def session(pth):
    import onnxruntime as ort, os, tempfile
    onnx_path = os.path.join(tempfile.gettempdir(), "impasto-srvgg.onnx")
    if not os.path.exists(onnx_path):
        build_onnx(load_pth(pth), onnx_path)
    return ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])


if __name__ == "__main__":
    pth, src, dst = sys.argv[1:4]
    upscale(session(pth), Image.open(src)).save(dst)
